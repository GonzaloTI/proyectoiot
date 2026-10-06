from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from functools import wraps
from datos import Database
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'iot_secret_key_antigravity_2026')

# Instancia de la Base de Datos (creará 'datos.db' por defecto)
db = Database()

# Configuración del estado global del relé
relay_state = {
    "manual_mode": False,       # False = Automático (por temperatura >= 40°C), True = Manual
    "manual_state": False,      # True = Encendido (ON), False = Apagado (OFF)
    "last_esp32_relay_status": False  # Último estado reportado por el ESP32
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
            if not user_id or not db.user_has_permission(user_id, codigo_permiso):
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
            
            has_any = any(db.user_has_permission(user_id, cod) for cod in codigos_list)
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
        return db.user_has_permission(user_id, codigo)
    return dict(has_permission=check_perm)

@app.before_request
def check_authentication():
    # Excluir rutas públicas: login, archivos estáticos, e ingesta de datos del ESP32 (/api/datos)
    if request.endpoint in ['login', 'logout', 'static', 'recibir_datos']:
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
        usuario = request.form.get('usuario', '').strip()
        password = request.form.get('password', '').strip()
        
        # Validación de campos y longitud máxima de 40 caracteres
        if not usuario or not password:
            error = "Por favor, complete todos los campos."
        elif len(usuario) > 40:
            error = "El usuario no debe exceder los 40 caracteres."
        elif len(password) > 40:
            error = "La contraseña no debe exceder los 40 caracteres."
        else:
            user, err_msg = db.verify_user_credentials(usuario, password)
            if user:
                session['user_id'] = user['id']
                session['usuario'] = user['usuario']
                session['roles'] = user.get('roles', [])
                session['is_admin'] = ('Admin' in user.get('roles', []))
                return redirect(url_for('index'))
            else:
                error = err_msg
                
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/datos', methods=['POST'])
def recibir_datos():
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No JSON payload received"}), 400

    temperatura = float(data.get('temperatura', 0))
    presion = float(data.get('presion', 0))
    altitud = float(data.get('altitud', 0))
    relay_activo = bool(data.get('relay_activo', False))
    co2 = float(data.get('co2', 400.0))
    humo = float(data.get('humo', 0.0))
    humedad_suelo = float(data.get('humedad_suelo', 0.0))

    # Actualizar estado del relé reportado
    relay_state["last_esp32_relay_status"] = relay_activo

    # Guardar en la base de datos a través de la clase Database
    try:
        db.save_reading(temperatura, presion, altitud, relay_activo, co2, humo, humedad_suelo)
    except Exception as e:
        print(f"Error guardando datos en la BD: {e}")

    # Determinar el comando y el modo a enviar al ESP32
    if relay_state["manual_mode"]:
        mode_str = "manual"
        comando = "ON" if relay_state["manual_state"] else "OFF"
    else:
        mode_str = "auto"
        comando = "OFF" # No relevante en modo auto

    return jsonify({
        "status": "ok",
        "mode": mode_str,
        "relay_command": comando
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    try:
        rows = db.get_history(limit=50)
        history_list = []
        for r in rows:
            history_list.append({
                "timestamp": r[0].split(" ")[1] if " " in r[0] else r[0], # Solo la hora para el eje X
                "temperatura": r[1],
                "presion": r[2],
                "altitud": r[3],
                "relay_activo": bool(r[4]),
                "co2": r[5] if len(r) > 5 else 400.0,
                "humo": r[6] if len(r) > 6 else 0.0,
                "humedad_suelo": r[7] if len(r) > 7 else 0.0
            })
    except Exception as e:
        print(f"Error obteniendo historial: {e}")
        history_list = []

    return jsonify({
        "history": history_list,
        "relay_state": relay_state
    })

@app.route('/api/relay/toggle', methods=['POST'])
@permission_required('CONTROL_RELE')
def toggle_relay():
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No JSON payload received"}), 400

    if "manual_mode" in data:
        relay_state["manual_mode"] = bool(data["manual_mode"])
    if "manual_state" in data:
        relay_state["manual_state"] = bool(data["manual_state"])

    return jsonify({
        "status": "ok",
        "relay_state": relay_state
    })

@app.route('/historial')
@permission_required('VER_HISTORIAL')
def historial():
    return render_template('historial.html')

@app.route('/api/history/dates', methods=['GET'])
@permission_required('VER_HISTORIAL')
def get_history_dates():
    try:
        dates = db.get_available_dates()
    except Exception as e:
        print(f"Error obteniendo fechas: {e}")
        dates = []
    return jsonify(dates)

@app.route('/api/history/daily', methods=['GET'])
@permission_required('VER_HISTORIAL')
def get_daily_history():
    date_str = request.args.get('date')
    if not date_str:
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        
    try:
        history = db.get_daily_data(date_str)
        stats = db.get_daily_stats(date_str)
    except Exception as e:
        print(f"Error obteniendo datos diarios: {e}")
        history = []
        stats = {}
        
    return jsonify({
        "date": date_str,
        "history": history,
        "stats": stats
    })

# ==================== RUTAS DE ADMINISTRACIÓN DE USUARIOS, ROLES Y PERMISOS ====================

@app.route('/usuarios')
@permission_required_any(['CREAR_USUARIOS', 'CREAR_ROLES', 'MODIFICAR_PERMISOS', 'DESACTIVAR_USUARIOS'])
def usuarios_page():
    users = db.get_all_users()
    roles = db.get_roles()
    all_permissions = db.get_all_permissions()
    return render_template('usuarios.html', users=users, roles=roles, all_permissions=all_permissions)

@app.route('/api/usuarios/crear', methods=['POST'])
@permission_required('CREAR_USUARIOS')
def crear_usuario():
    usuario = request.form.get('usuario', '').strip()
    password = request.form.get('password', '').strip()
    role_ids = request.form.getlist('role_ids')

    if not usuario or not password:
        flash("Por favor proporcione usuario y contraseña.", "danger")
        return redirect(url_for('usuarios_page'))

    if len(usuario) > 40:
        flash("El nombre de usuario no puede exceder los 40 caracteres.", "danger")
        return redirect(url_for('usuarios_page'))

    if len(password) > 40:
        flash("La contraseña no puede exceder los 40 caracteres.", "danger")
        return redirect(url_for('usuarios_page'))

    user_id, error = db.create_user(usuario, password, estado=1, role_ids=role_ids)
    if error:
        flash(f"Error creando usuario: {error}", "danger")
    else:
        flash(f"Usuario '{usuario}' creado exitosamente con sus roles.", "success")

    return redirect(url_for('usuarios_page'))

@app.route('/api/roles/crear', methods=['POST'])
@permission_required('CREAR_ROLES')
def crear_rol():
    rol_name = request.form.get('rol', '').strip()
    descripcion = request.form.get('descripcion', '').strip()

    if not rol_name:
        flash("El nombre del rol es obligatorio.", "danger")
        return redirect(url_for('usuarios_page'))

    if len(rol_name) > 40:
        flash("El nombre del rol no debe superar los 40 caracteres.", "danger")
        return redirect(url_for('usuarios_page'))

    role_id, error = db.create_role(rol_name, descripcion)
    if error:
        flash(f"Error creando rol: {error}", "danger")
    else:
        flash(f"Rol '{rol_name}' creado exitosamente.", "success")

    return redirect(url_for('usuarios_page'))

@app.route('/api/usuarios/toggle_status', methods=['POST'])
@permission_required('DESACTIVAR_USUARIOS')
def toggle_usuario_status():
    user_id = request.form.get('user_id')
    if user_id:
        new_status = db.toggle_user_status(user_id)
        msg = "activada" if new_status else "desactivada"
        flash(f"La cuenta de usuario ha sido {msg}.", "info")
    return redirect(url_for('usuarios_page'))

@app.route('/api/usuarios/permisos', methods=['POST'])
@permission_required('MODIFICAR_PERMISOS')
def guardar_permisos_usuario():
    user_id = request.form.get('user_id')
    if not user_id:
        flash("Usuario no especificado.", "danger")
        return redirect(url_for('usuarios_page'))
        
    all_perms = db.get_all_permissions()
    perms_to_save = {}
    for p in all_perms:
        pid = p["id"]
        # Verificar si se marco el checkbox del permiso
        if f'perm_{pid}' in request.form:
            # Obtener fecha final (si se dejo vacia o se selecciono indefinido)
            is_indefinite = request.form.get(f'indefinite_{pid}') == '1'
            fechafinal = request.form.get(f'fechafinal_{pid}', '').strip()
            if is_indefinite or not fechafinal:
                perms_to_save[pid] = None
            else:
                perms_to_save[pid] = fechafinal

    db.update_user_permissions(user_id, perms_to_save)
    flash("Permisos del usuario actualizados correctamente.", "success")
    return redirect(url_for('usuarios_page'))

@app.route('/api/usuarios/editar', methods=['POST'])
@permission_required_any(['CREAR_USUARIOS', 'MODIFICAR_PERMISOS'])
def editar_usuario():
    user_id = request.form.get('user_id')
    new_password = request.form.get('password', '').strip()
    role_ids = request.form.getlist('role_ids')

    if not user_id:
        flash("Usuario no especificado.", "danger")
        return redirect(url_for('usuarios_page'))

    if new_password and len(new_password) > 40:
        flash("La nueva contraseña no puede exceder los 40 caracteres.", "danger")
        return redirect(url_for('usuarios_page'))

    success, error = db.update_user(user_id, new_password=new_password, role_ids=role_ids)
    if error:
        flash(f"Error actualizando usuario: {error}", "danger")
    else:
        flash("Datos del usuario actualizados correctamente.", "success")

    return redirect(url_for('usuarios_page'))

if __name__ == '__main__':
    # Escucha en todas las interfaces de red en el puerto 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
