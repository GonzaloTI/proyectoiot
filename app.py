from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from functools import wraps
# pyrefly: ignore [missing-import]
from negocio.Nsession import procesar_login, cerrar_sesion
# pyrefly: ignore [missing-import]
from negocio.Ndatos import (
    procesar_y_guardar_datos,
    obtener_historial,
    actualizar_estado_rele,
    obtener_fechas_historial,
    obtener_historial_diario
)
# pyrefly: ignore [missing-import]
from negocio.Nnotificaciones import (
    init_push_db,
    procesar_suscripcion,
    enviar_notificacion_push,
    obtener_suscripciones_debug,
    VAPID_PUBLIC_KEY
)
# pyrefly: ignore [missing-import]
from negocio.Nusuarios import (
    obtener_datos_pagina_usuarios,
    procesar_creacion_usuario,
    procesar_creacion_rol,
    procesar_cambio_estado_usuario,
    procesar_guardado_permisos_usuario,
    procesar_edicion_usuario,
    verificar_permiso_usuario
)
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'iot_secret_key_antigravity_2026')

# Inicializar tabla de suscripciones Web Push
init_push_db()

# Configuración del estado global de los relés (Relé 1 y Relé 2)
relay_state = {
    "manual_mode": False,              # False = Automático (por temperatura >= 40°C), True = Manual
    "manual_state": False,             # Relé 1: True = Encendido (ON), False = Apagado (OFF)
    "manual_state_2": False,           # Relé 2: True = Encendido (ON), False = Apagado (OFF)
    "last_esp32_relay_status": False,  # Último estado reportado por el ESP32 para Relé 1
    "last_esp32_relay_2_status": False # Último estado reportado por el ESP32 para Relé 2
}

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id') or not session.get('is_admin'):
            if request.path.startswith('/api/'):
                return jsonify({"status": "error", "message": "Acceso restringido a administradores."}), 403
            flash("Acceso restringido únicamente a usuarios administradores.", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def permission_required(codigo_permiso):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = session.get('user_id')
            if not user_id or not verificar_permiso_usuario(user_id, codigo_permiso):
                if request.is_json or request.headers.get('Accept') == 'application/json':
                    return jsonify({"status": "error", "message": f"No posee el permiso requerido: {codigo_permiso}"}), 403
                flash(f"No posee el permiso requerido: {codigo_permiso}", "danger")
                if request.path.startswith('/api/usuarios') or request.path.startswith('/api/roles'):
                    return redirect(url_for('usuarios_page'))
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def permission_required_any(codigos_list):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = session.get('user_id')
            if not user_id:
                return redirect(url_for('login'))
            
            has_any = any(verificar_permiso_usuario(user_id, cod) for cod in codigos_list)
            if not has_any:
                if request.is_json or request.headers.get('Accept') == 'application/json':
                    return jsonify({"status": "error", "message": "No posee los permisos requeridos."}), 403
                flash("No tienes permiso suficiente para acceder a esta sección.", "danger")
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.context_processor
def inject_permissions():
    def check_perm(codigo):
        user_id = session.get('user_id')
        if not user_id:
            return False
        return verificar_permiso_usuario(user_id, codigo)
    return dict(has_permission=check_perm, vapid_public_key=VAPID_PUBLIC_KEY)

@app.before_request
def check_authentication():
    # Excluir rutas públicas: login, archivos estáticos, ingesta de datos y suscripción a notificaciones
    if request.endpoint in ['login', 'logout', 'static', 'recibir_datos', 'subscribe', 'send_notification', 'debug_subscriptions']:
        return None
    
    # Si el usuario no ha iniciado sesión
    if not session.get('user_id'):
        if request.path.startswith('/api/'):
            return jsonify({"status": "error", "message": "No autorizado. Debe iniciar sesión."}), 401
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('index'))
        
    error = None
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        password = request.form.get('password')
        
        exito, error = procesar_login(usuario, password)
        if exito:
            return redirect(url_for('index'))
                
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    cerrar_sesion()
    return redirect(url_for('login'))

@app.route('/')
def index():
    return render_template('index.html', vapid_public_key=VAPID_PUBLIC_KEY)

@app.route('/subscribe', methods=['POST'])
def subscribe():
    res, status_code = procesar_suscripcion(request.get_json())
    return jsonify(res), status_code

@app.route('/send-notification', methods=['POST'])
def send_notification():
    data = request.get_json(silent=True) or {}
    title = data.get('title')
    body = data.get('body')
    tipo = data.get('tipo', 'aviso')
    
    res = enviar_notificacion_push(title=title, body=body, tipo=tipo)
    return jsonify(res)

@app.route('/debug/subscriptions', methods=['GET'])
def debug_subscriptions():
    res = obtener_suscripciones_debug()
    return jsonify(res)

@app.route('/api/datos', methods=['POST'])
def recibir_datos():
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No JSON payload received"}), 400

    respuesta = procesar_y_guardar_datos(data, relay_state)
    return jsonify(respuesta)

@app.route('/api/history', methods=['GET'])
def get_history():
    respuesta = obtener_historial(relay_state)
    return jsonify(respuesta)

@app.route('/api/relay/toggle', methods=['POST'])
@permission_required('CONTROL_RELE')
def toggle_relay():
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No JSON payload received"}), 400

    respuesta = actualizar_estado_rele(relay_state, data)
    return jsonify(respuesta)

@app.route('/historial')
@permission_required('VER_HISTORIAL')
def historial():
    return render_template('historial.html')

@app.route('/api/history/dates', methods=['GET'])
@permission_required('VER_HISTORIAL')
def get_history_dates():
    dates = obtener_fechas_historial()
    return jsonify(dates)

@app.route('/api/history/daily', methods=['GET'])
@permission_required('VER_HISTORIAL')
def get_daily_history():
    date_str = request.args.get('date')
    resultado = obtener_historial_diario(date_str)
    return jsonify(resultado)

# ==================== RUTAS DE ADMINISTRACIÓN DE USUARIOS, ROLES Y PERMISOS ====================

@app.route('/usuarios')
@permission_required_any(['CREAR_USUARIOS', 'CREAR_ROLES', 'MODIFICAR_PERMISOS', 'DESACTIVAR_USUARIOS'])
def usuarios_page():
    users, roles, all_permissions = obtener_datos_pagina_usuarios()
    return render_template('usuarios.html', users=users, roles=roles, all_permissions=all_permissions)

@app.route('/api/usuarios/crear', methods=['POST'])
@permission_required('CREAR_USUARIOS')
def crear_usuario():
    usuario = request.form.get('usuario')
    password = request.form.get('password')
    role_ids = request.form.getlist('role_ids')

    exito, mensaje, categoria = procesar_creacion_usuario(usuario, password, role_ids)
    flash(mensaje, categoria)
    return redirect(url_for('usuarios_page'))

@app.route('/api/roles/crear', methods=['POST'])
@permission_required('CREAR_ROLES')
def crear_rol():
    rol_name = request.form.get('rol')
    descripcion = request.form.get('descripcion')

    exito, mensaje, categoria = procesar_creacion_rol(rol_name, descripcion)
    flash(mensaje, categoria)
    return redirect(url_for('usuarios_page'))

@app.route('/api/usuarios/toggle_status', methods=['POST'])
@permission_required('DESACTIVAR_USUARIOS')
def toggle_usuario_status():
    user_id = request.form.get('user_id')
    exito, mensaje, categoria = procesar_cambio_estado_usuario(user_id)
    flash(mensaje, categoria)
    return redirect(url_for('usuarios_page'))

@app.route('/api/usuarios/permisos', methods=['POST'])
@permission_required('MODIFICAR_PERMISOS')
def guardar_permisos_usuario():
    user_id = request.form.get('user_id')
    exito, mensaje, categoria = procesar_guardado_permisos_usuario(user_id, request.form)
    flash(mensaje, categoria)
    return redirect(url_for('usuarios_page'))

@app.route('/api/usuarios/editar', methods=['POST'])
@permission_required_any(['CREAR_USUARIOS', 'MODIFICAR_PERMISOS'])
def editar_usuario():
    user_id = request.form.get('user_id')
    new_password = request.form.get('password')
    role_ids = request.form.getlist('role_ids')

    exito, mensaje, categoria = procesar_edicion_usuario(user_id, new_password, role_ids)
    flash(mensaje, categoria)
    return redirect(url_for('usuarios_page'))

if __name__ == '__main__':
    # Escucha en todas las interfaces de red en el puerto 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
