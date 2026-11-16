from datos import Database

class Dnotificaciones:
    """
    Modelo de datos para la tabla 'suscripcion' (Suscripciones Web Push asociadas a usuarios).
    Responsable de persistir y recuperar los endpoints y llaves de suscripción.
    """
    def __init__(self, db_name='postgres'):
        self.db = Database(db_name=db_name)

    def inicializar_tabla(self):
        """
        Garantiza que la tabla 'suscripcion' esté creada en la base de datos.
        """
        self.db.init_db()

    def guardar_suscripcion(self, endpoint, p256dh, auth, id_usuario=None):
        """
        Inserta o actualiza una suscripción Web Push vinculada a un id_usuario y retorna el conteo total.
        """
        return self.db.save_push_subscription(endpoint, p256dh, auth, id_usuario=id_usuario)

    def obtener_suscripciones(self, id_usuario=None, user_ids=None):
        """
        Obtiene todas las suscripciones Web Push activas registradas (o filtradas por id_usuario / user_ids).
        """
        return self.db.get_push_subscriptions(id_usuario=id_usuario, user_ids=user_ids)

    def obtener_usuarios_para_notificaciones(self):
        """
        Obtiene la lista de usuarios y el estado de sus suscripciones para elegir destinatarios.
        """
        return self.db.get_users_for_notifications()

    def eliminar_suscripcion(self, endpoint):
        """
        Elimina una suscripción inválida o expirada.
        """
        return self.db.delete_push_subscription(endpoint)

    # Alias en inglés para compatibilidad
    init_db = inicializar_tabla
    save_push_subscription = guardar_suscripcion
    get_push_subscriptions = obtener_suscripciones

# Alias correspondiente al nombre de la tabla
Dsuscripciones = Dnotificaciones
