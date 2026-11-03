from datos import Database

class Dpermisos:
    """
    Modelo de datos para la tabla 'permisos' y la tabla intermedia 'usuario_permiso'.
    Responsable de la persistencia y lectura de permisos del sistema.
    """
    def __init__(self, db_name='datos.db'):
        self.db = Database(db_name=db_name)

    def obtener_todos_los_permisos(self):
        """
        Obtiene la lista de todos los permisos registrados en el catálogo.
        """
        return self.db.get_all_permissions()

    def obtener_permisos_usuario(self, user_id):
        """
        Obtiene los permisos asignados a un usuario específico y verifica su vigencia.
        """
        return self.db.get_user_permissions(user_id)

    def usuario_tiene_permiso(self, user_id, codigo_permiso):
        """
        Verifica si un usuario posee un permiso activo o cuenta con el rol de Administrador.
        """
        return self.db.user_has_permission(user_id, codigo_permiso)

    def actualizar_permisos_usuario(self, user_id, permissions_dict):
        """
        Actualiza y persiste los permisos asignados a un usuario en la tabla 'usuario_permiso'.
        """
        return self.db.update_user_permissions(user_id, permissions_dict)

    # Alias en inglés para compatibilidad
    get_all_permissions = obtener_todos_los_permisos
    get_user_permissions = obtener_permisos_usuario
    user_has_permission = usuario_tiene_permiso
    update_user_permissions = actualizar_permisos_usuario
