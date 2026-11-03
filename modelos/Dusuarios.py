from datos import Database

class Dusuarios:
    """
    Modelo de datos para la tabla 'usuario' y sus tablas intermedias ('usuario_rol', 'usuario_permiso').
    Responsable de la persistencia, validación de credenciales y administración de usuarios.
    """
    def __init__(self, db_name='datos.db'):
        self.db = Database(db_name=db_name)

    def obtener_todos_los_usuarios(self):
        """
        Obtiene todos los usuarios registrados con sus roles asignados.
        """
        return self.db.get_all_users()

    def obtener_usuario_por_username(self, username):
        """
        Busca un usuario por su nombre de usuario.
        """
        return self.db.get_user_by_username(username)

    def obtener_roles_usuario(self, user_id):
        """
        Obtiene los roles asignados a un usuario específico.
        """
        return self.db.get_user_roles(user_id)

    def crear_usuario(self, usuario, password, estado=1, role_ids=None):
        """
        Inserta un nuevo usuario con contraseña hasheada y asigna sus roles.
        """
        return self.db.create_user(usuario, password, estado=estado, role_ids=role_ids)

    def alternar_estado_usuario(self, user_id):
        """
        Alterna el estado (activo/inactivo) de una cuenta de usuario.
        """
        return self.db.toggle_user_status(user_id)

    def actualizar_usuario(self, user_id, new_password=None, role_ids=None):
        """
        Actualiza la contraseña y/o los roles de un usuario existente.
        """
        return self.db.update_user(user_id, new_password=new_password, role_ids=role_ids)

    def verificar_credenciales(self, usuario, password):
        """
        Verifica si el usuario y la contraseña proporcionados son válidos.
        """
        return self.db.verify_user_credentials(usuario, password)

    def usuario_tiene_permiso(self, user_id, codigo_permiso):
        """
        Verifica si el usuario cuenta con un permiso específico activo.
        """
        return self.db.user_has_permission(user_id, codigo_permiso)

    def actualizar_permisos_usuario(self, user_id, permissions_dict):
        """
        Actualiza los permisos asignados a un usuario.
        """
        return self.db.update_user_permissions(user_id, permissions_dict)

    # Alias en inglés para compatibilidad
    get_all_users = obtener_todos_los_usuarios
    get_user_by_username = obtener_usuario_por_username
    get_user_roles = obtener_roles_usuario
    create_user = crear_usuario
    toggle_user_status = alternar_estado_usuario
    update_user = actualizar_usuario
    verify_user_credentials = verificar_credenciales
    user_has_permission = usuario_tiene_permiso
    update_user_permissions = actualizar_permisos_usuario
