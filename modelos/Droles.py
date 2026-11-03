from datos import Database

class Droles:
    """
    Modelo de datos para la tabla 'rol'.
    Responsable de la persistencia y lectura de roles en la base de datos.
    """
    def __init__(self, db_name='datos.db'):
        self.db = Database(db_name=db_name)

    def obtener_roles(self):
        """
        Obtiene la lista de todos los roles registrados.
        """
        return self.db.get_roles()

    def crear_rol(self, rol, descripcion=""):
        """
        Inserta un nuevo rol en la base de datos.
        """
        return self.db.create_role(rol, descripcion)

    # Alias en inglés para compatibilidad
    get_roles = obtener_roles
    create_role = crear_rol
