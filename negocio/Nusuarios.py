from modelos.Dusuarios import Dusuarios
from modelos.Droles import Droles
from modelos.Dpermisos import Dpermisos

# Instancias de los modelos de datos para la capa de negocio
d_usuarios = Dusuarios()
d_roles = Droles()
d_permisos = Dpermisos()

def obtener_datos_pagina_usuarios():
    """
    Obtiene todos los usuarios, roles y permisos requeridos para renderizar la página de administración de usuarios.
    """
    users = d_usuarios.obtener_todos_los_usuarios()
    roles = d_roles.obtener_roles()
    all_permissions = d_permisos.obtener_todos_los_permisos()
    return users, roles, all_permissions


def procesar_creacion_usuario(usuario, password, role_ids):
    """
    Procesa la creación de un nuevo usuario, realizando las validaciones de negocio correspondientes.
    
    Retorna:
        tuple: (exito: bool, mensaje: str, categoria_flash: str)
    """
    usuario = (usuario or '').strip()
    password = (password or '').strip()

    if not usuario or not password:
        return False, "Por favor proporcione usuario y contraseña.", "danger"

    if len(usuario) > 40:
        return False, "El nombre de usuario no puede exceder los 40 caracteres.", "danger"

    if len(password) > 40:
        return False, "La contraseña no puede exceder los 40 caracteres.", "danger"

    user_id, error = d_usuarios.crear_usuario(usuario, password, estado=1, role_ids=role_ids)
    if error:
        return False, f"Error creando usuario: {error}", "danger"

    return True, f"Usuario '{usuario}' creado exitosamente con sus roles.", "success"


def procesar_creacion_rol(rol_name, descripcion):
    """
    Procesa la creación de un nuevo rol con sus validaciones de negocio.
    """
    rol_name = (rol_name or '').strip()
    descripcion = (descripcion or '').strip()

    if not rol_name:
        return False, "El nombre del rol es obligatorio.", "danger"

    if len(rol_name) > 40:
        return False, "El nombre del rol no debe superar los 40 caracteres.", "danger"

    role_id, error = d_roles.crear_rol(rol_name, descripcion)
    if error:
        return False, f"Error creando rol: {error}", "danger"

    return True, f"Rol '{rol_name}' creado exitosamente.", "success"


def procesar_cambio_estado_usuario(user_id):
    """
    Alterna el estado de activación/suspensión de una cuenta de usuario.
    """
    if not user_id:
        return False, "Usuario no especificado.", "danger"

    new_status = d_usuarios.alternar_estado_usuario(user_id)
    msg = "activada" if new_status else "desactivada"
    return True, f"La cuenta de usuario ha sido {msg}.", "info"


def procesar_guardado_permisos_usuario(user_id, form_data):
    """
    Procesa los permisos asignados o revocados a un usuario desde el formulario.
    """
    if not user_id:
        return False, "Usuario no especificado.", "danger"

    all_perms = d_permisos.obtener_todos_los_permisos()
    perms_to_save = {}

    for p in all_perms:
        pid = p["id"]
        # Verificar si se marcó el checkbox del permiso
        if f'perm_{pid}' in form_data:
            is_indefinite = form_data.get(f'indefinite_{pid}') == '1'
            fechafinal = form_data.get(f'fechafinal_{pid}', '').strip()
            if is_indefinite or not fechafinal:
                perms_to_save[pid] = None
            else:
                perms_to_save[pid] = fechafinal

    d_permisos.actualizar_permisos_usuario(user_id, perms_to_save)
    return True, "Permisos del usuario actualizados correctamente.", "success"


def procesar_edicion_usuario(user_id, new_password, role_ids):
    """
    Procesa la actualización de la contraseña y roles de un usuario existente.
    """
    if not user_id:
        return False, "Usuario no especificado.", "danger"

    new_password = (new_password or '').strip()
    if new_password and len(new_password) > 40:
        return False, "La nueva contraseña no puede exceder los 40 caracteres.", "danger"

    success, error = d_usuarios.actualizar_usuario(user_id, new_password=new_password, role_ids=role_ids)
    if error:
        return False, f"Error actualizando usuario: {error}", "danger"

    return True, "Datos del usuario actualizados correctamente.", "success"


def verificar_permiso_usuario(user_id, codigo_permiso):
    """
    Verifica si un usuario posee un permiso activo o rol Administrador.
    """
    return d_permisos.usuario_tiene_permiso(user_id, codigo_permiso)


