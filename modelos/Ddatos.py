from datos import Database

class Ddatos:
    """
    Modelo de datos para las lecturas de sensores y telemetría (Readings).
    Esta clase es la responsable directa de instanciar y comunicarse con la base de datos.
    """
    def __init__(self, db_name='datos.db'):
        # Instancia directa de la Base de Datos
        self.db = Database(db_name=db_name)

    def guardar_lectura(self, temperatura, presion, altitud, relay_activo, co2, humo, humedad_suelo):
        """
        Inserta una nueva lectura de telemetría en la tabla de lecturas.
        """
        return self.db.save_reading(
            temperatura=temperatura,
            presion=presion,
            altitud=altitud,
            relay_activo=relay_activo,
            co2=co2,
            humo=humo,
            humedad_suelo=humedad_suelo
        )

    def obtener_historial(self, limit=50):
        """
        Obtiene las últimas 'limit' lecturas registradas.
        """
        return self.db.get_history(limit=limit)

    def obtener_fechas_disponibles(self):
        """
        Obtiene la lista de fechas únicas registradas con lecturas.
        """
        return self.db.get_available_dates()

    def obtener_datos_diarios(self, date_str):
        """
        Obtiene las lecturas detalladas de una fecha específica (YYYY-MM-DD).
        """
        return self.db.get_daily_data(date_str)

    def obtener_estadisticas_diarias(self, date_str):
        """
        Obtiene los valores mínimos, máximos y promedios para una fecha específica.
        """
        return self.db.get_daily_stats(date_str)

    # Alias en inglés para compatibilidad directa
    save_reading = guardar_lectura
    get_history = obtener_historial
    get_available_dates = obtener_fechas_disponibles
    get_daily_data = obtener_datos_diarios
    get_daily_stats = obtener_estadisticas_diarias
