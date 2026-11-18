from flask import (
    Flask, request, jsonify, render_template, redirect, url_for,
    session, flash, send_from_directory, make_response
)
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
    obtener_usuarios_para_notificaciones,
    obtener_config_alertas_sensores,
    guardar_config_alertas_sensores,
    simular_prueba_push,
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
# pyrefly: ignore [missing-import]
from negocio.Ndetecciones import (
    procesar_subida_deteccion,
    obtener_ultima_deteccion,
    obtener_historial_detecciones,
    obtener_historial_paginado,
    obtener_config_notificaciones_detecciones,
    guardar_config_notificaciones_detecciones
)
# pyrefly: ignore [missing-import]
from negocio.Nactuadores import (
    obtener_config_actuadores,
    guardar_config_actuadores
)
import os
import json

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
    # Excluir rutas públicas: login, archivos estáticos, ingesta de datos, subida de detecciones y suscripción a notificaciones
    if request.endpoint in ['login', 'logout', 'static', 'service_worker', 'favicon', 'recibir_datos', 'subscribe', 'send_notification', 'debug_subscriptions', 'api_destinatarios_notificaciones', 'subir_deteccion', 'api_obtener_ultima_deteccion', 'actuadores_page', 'api_actuadores_config', 'api_actuadores_estado', 'api_detecciones_notificaciones_config']:
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

@app.route('/sw.js')
def service_worker():
    """
    Entrega el Service Worker con cabeceras de alcance global (Service-Worker-Allowed: /)
    para que pueda controlar todas las rutas de la aplicación y gestionar Web Push.
    """
    response = make_response(send_from_directory('static', 'sw.js'))
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@app.route('/favicon.ico')
def favicon():
    """
    Entrega el icono de la aplicación para navegadores que solicitan /favicon.ico por defecto.
    """
    return send_from_directory('static', 'icono.jpg', mimetype='image/jpeg')

@app.route('/')
def index():
    return render_template('index.html', vapid_public_key=VAPID_PUBLIC_KEY)

@app.route('/subscribe', methods=['POST'])
def subscribe():
    data = request.get_json(silent=True) or {}
    user_id = session.get('user_id') or data.get('id_usuario')
    res, status_code = procesar_suscripcion(data, user_id=user_id)
    return jsonify(res), status_code

@app.route('/send-notification', methods=['POST'])
def send_notification():
    data = request.get_json(silent=True) or {}
    title = data.get('title')
    body = data.get('body')
    tipo = data.get('tipo', 'aviso')
    destinatarios = data.get('destinatarios', 'todos')
    user_ids = data.get('user_ids', [])
    
    res = enviar_notificacion_push(
        title=title,
        body=body,
        tipo=tipo,
        destinatarios=destinatarios,
        user_ids=user_ids
    )
    return jsonify(res)

@app.route('/api/notificaciones/destinatarios', methods=['GET'])
def api_destinatarios_notificaciones():
    usuarios = obtener_usuarios_para_notificaciones()
    return jsonify({"status": "ok", "usuarios": usuarios})

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

# ==================== RUTAS DE DETECCIONES (VISIÓN ARTIFICIAL) ====================

@app.route('/api/detecciones/subir', methods=['POST'])
def subir_deteccion():
    """
    Endpoint público para que la Jetson Nano suba imágenes detectadas y metadatos JSON.
    """
    file = request.files.get('imagen') or request.files.get('file')
    if not file:
        return jsonify({"status": "error", "message": "No se recibió archivo en el campo 'imagen' o 'file'"}), 400

    # Los metadatos pueden venir como campos de formulario individuales o como JSON string en 'datos'
    if 'datos' in request.form:
        try:
            datos = json.loads(request.form.get('datos'))
        except Exception:
            datos = request.form.to_dict()
    else:
        datos = request.form.to_dict()

    resultado, status_code = procesar_subida_deteccion(file, datos)
    return jsonify(resultado), status_code

@app.route('/api/detecciones/ultima', methods=['GET'])
def api_obtener_ultima_deteccion():
    """
    Retorna la última detección registrada en formato JSON para el panel en vivo.
    """
    resultado = obtener_ultima_deteccion()
    return jsonify(resultado)

@app.route('/api/detecciones/historial', methods=['GET'])
def api_obtener_historial_detecciones():
    """
    Retorna el historial de detecciones con soporte de paginación, filtros y ordenamiento.
    """
    # Si viene con parámetro 'limit' clásico y no especifica 'page', usamos la función legacy
    if 'limit' in request.args and 'page' not in request.args:
        limit = request.args.get('limit', default=50, type=int)
        resultado = obtener_historial_detecciones(limit=limit)
        return jsonify(resultado)

    page = request.args.get('page', default=1, type=int)
    per_page = request.args.get('per_page', default=10, type=int)
    fecha_desde = request.args.get('fecha_desde', default=None, type=str)
    fecha_hasta = request.args.get('fecha_hasta', default=None, type=str)
    clase = request.args.get('clase', default=None, type=str)
    busqueda = request.args.get('busqueda', default=None, type=str)
    sort_col = request.args.get('sort_col', default=None, type=str)
    sort_dir = request.args.get('sort_dir', default=None, type=str)

    resultado = obtener_historial_paginado(
        page=page,
        per_page=per_page,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        clase=clase,
        busqueda=busqueda,
        sort_col=sort_col,
        sort_dir=sort_dir
    )
    return jsonify(resultado)

@app.route('/detecciones')
def detecciones_page():
    """
    Página web de monitoreo de Visión Artificial: Detección en vivo e Historial.
    """
    return render_template('detecciones.html')

@app.route('/api/detecciones/notificaciones/config', methods=['GET', 'POST'])
def api_detecciones_notificaciones_config():
    """
    Obtiene o actualiza la configuración de frecuencia y destinatarios de notificaciones automáticas para Visión Artificial.
    """
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        if not data:
            return jsonify({"status": "error", "message": "Datos JSON inválidos"}), 400
        exito, msg = guardar_config_notificaciones_detecciones(data)
        if exito:
            return jsonify({"status": "ok", "message": msg, "config": obtener_config_notificaciones_detecciones()})
        return jsonify({"status": "error", "message": msg}), 500

    return jsonify({"status": "ok", "config": obtener_config_notificaciones_detecciones()})

# ==================== RUTAS DE ALERTAS DE SENSORES Y UMBRALES ====================

@app.route('/api/alertas/config', methods=['GET', 'POST'])
def api_alertas_config():
    """
    Obtiene o actualiza la configuración de alertas de sensores (umbrales mín/máx, frecuencia, condición y destinatarios).
    Solo usuarios con rol Administrador pueden guardar modificaciones.
    """
    if request.method == 'POST':
        if not session.get('user_id') or not session.get('is_admin'):
            return jsonify({
                "status": "error",
                "message": "Acceso restringido: únicamente administradores pueden modificar los umbrales de alerta."
            }), 403

        data = request.get_json(silent=True) or {}
        if not data:
            return jsonify({"status": "error", "message": "Payload JSON inválido"}), 400

        exito, msg = guardar_config_alertas_sensores(data)
        if exito:
            return jsonify({
                "status": "ok",
                "message": msg,
                "config": obtener_config_alertas_sensores()
            })
        return jsonify({"status": "error", "message": msg}), 500

    # GET: Retorna configuración actual, bandera is_admin y lista de usuarios
    usuarios = obtener_usuarios_para_notificaciones()
    return jsonify({
        "status": "ok",
        "config": obtener_config_alertas_sensores(),
        "is_admin": bool(session.get('is_admin', False)),
        "current_user": session.get('usuario', 'invitado'),
        "usuarios": usuarios
    })

@app.route('/api/alertas/probar', methods=['POST'])
def api_alertas_probar():
    """
    Permite enviar una notificación push simulada con un escenario específico (anomalía, normal, esp32 offline, jetson offline).
    """
    data = request.get_json(silent=True) or {}
    escenario = data.get('escenario', 'anomalia')
    destinatarios = data.get('destinatarios')
    user_ids = data.get('user_ids')

    resultado = simular_prueba_push(escenario=escenario, destinatarios=destinatarios, user_ids=user_ids)
    return jsonify({
        "status": "ok",
        "escenario": escenario,
        "resultado": resultado
    })

@app.route('/actuadores')
@app.route('/control-actuadores')
def actuadores_page():
    """
    Página web oficial de Automatización Inteligente y Control de Actuadores (Relé 1 y Relé 2).
    """
    config = obtener_config_actuadores()
    return render_template('actuadores.html', config=config)

@app.route('/api/actuadores/config', methods=['GET', 'POST'])
def api_actuadores_config():
    """
    Obtiene o actualiza la configuración de Automatización Inteligente de los relés.
    """
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        if not data:
            return jsonify({"status": "error", "message": "Payload JSON inválido"}), 400
        exito, msg = guardar_config_actuadores(data)
        if exito:
            return jsonify({"status": "ok", "message": msg, "config": obtener_config_actuadores()})
        return jsonify({"status": "error", "message": msg}), 500
    
    # GET
    return jsonify({"status": "ok", "config": obtener_config_actuadores()})

@app.route('/api/actuadores/estado', methods=['GET'])
def api_actuadores_estado():
    """
    Retorna el estado en tiempo real de los relés y la última evaluación de la Automatización Inteligente.
    """
    return jsonify({
        "status": "ok",
        "relay_state": relay_state,
        "smart_eval": relay_state.get("smart_eval"),
        "config": obtener_config_actuadores()
    })

if __name__ == '__main__':
    # Escucha en todas las interfaces de red en el puerto 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
