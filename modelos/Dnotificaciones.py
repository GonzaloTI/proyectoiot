from datos import Database

class Dnotificaciones:
    """
    Modelo de datos para la tabla 'subscriptions' (Suscripciones Web Push).
    Responsable de persistir y recuperar los endpoints y llaves de suscripción.
    """
    def __init__(self, db_name='datos.db'):
        self.db = Database(db_name=db_name)

    def inicializar_tabla(self):
        """
        Garantiza que la tabla de suscripciones esté creada en la base de datos.
        """
        self.db.init_db()

    def guardar_suscripcion(self, endpoint, p256dh, auth):
        """
        Inserta o actualiza una suscripción Web Push y retorna el conteo total.
        """
        return self.db.save_push_subscription(endpoint, p256dh, auth)

    def obtener_suscripciones(self):
        """
        Obtiene todas las suscripciones Web Push activas registradas.
        """
        return self.db.get_push_subscriptions()

    # Alias en inglés para compatibilidad
    init_db = inicializar_tabla
    save_push_subscription = guardar_suscripcion
    get_push_subscriptions = obtener_suscripciones

# Alias correspondiente al nombre de la tabla
Dsuscripciones = Dnotificaciones
