from datos import Database

class Ddetecciones:
    """
    Modelo de datos para las detecciones de visión artificial (Fragaria y otros modelos).
    Responsable directo de comunicarse con la base de datos para la tabla 'detecciones'.
    """
    def __init__(self, db_name='datos.db'):
        self.db = Database(db_name=db_name)

    def guardar_deteccion(self, path, modelo, total, clase, conf, enfermedad):
        """
        Inserta un nuevo registro de detección con su respectivo path de imagen.
        """
        return self.db.save_detection(
            path=path,
            modelo=modelo,
            total=total,
            clase=clase,
            conf=conf,
            enfermedad=enfermedad
        )

    def obtener_ultima_deteccion(self):
        """
        Obtiene el último registro de detección para visualización en vivo.
        """
        return self.db.get_latest_detection()

    def obtener_historial_detecciones(self, limit=50):
        """
        Obtiene los últimos 'limit' registros de detecciones ordenados descendentemente.
        """
        return self.db.get_detections_history(limit=limit)

    def obtener_historial_paginado(self, page=1, per_page=10, fecha_desde=None, fecha_hasta=None, clase=None, busqueda=None, sort_col=None, sort_dir=None):
        """
        Obtiene el historial de detecciones con paginación, filtros y ordenamiento dinámico.
        """
        return self.db.get_detections_history_paginated(
            page=page,
            per_page=per_page,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            clase=clase,
            busqueda=busqueda,
            sort_col=sort_col,
            sort_dir=sort_dir
        )

