import os
import uuid
import time
from datetime import datetime
from werkzeug.utils import secure_filename
from modelos.Ddetecciones import Ddetecciones

# Directorio base para almacenamiento de imágenes de detecciones
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
UPLOADS_DIR = os.path.join(BASE_DIR, 'static', 'uploads', 'detecciones')
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Instancia del modelo de datos Ddetecciones
d_detecciones = Ddetecciones()

# Variables globales para control de persistencia inteligente y streaming en vivo
consecutive_empty_count = 0
live_stream_cache = None
last_jetson_upload_time = None

def procesar_subida_deteccion(file_storage, datos):
    """
    Procesa y guarda la imagen y metadatos de detección enviados por la Jetson Nano.
    
    Lógica inteligente de almacenamiento:
      - Si detecta objetos (total > 0): Siempre guarda la imagen en disco y en la BD.
      - Si no detecta objetos (total == 0): Guarda un máximo de 4 fotogramas consecutivos.
      - A partir del 5to fotograma consecutivo sin detección: No guarda en BD ni genera
        nuevos archivos en disco; únicamente sobrescribe 'live_latest.jpg' para que
        la transmisión en vivo en el navegador continúe sin consumir espacio de memoria.
    """
    global consecutive_empty_count, live_stream_cache, last_jetson_upload_time
    last_jetson_upload_time = time.time()

    if not file_storage or file_storage.filename == '':
        return {"status": "error", "message": "No se recibió ningún archivo de imagen válido."}, 400

    # Extraer y normalizar campos del diccionario
    modelo = str(datos.get('modelo', 'fragaria')).strip().lower()
    try:
        total = int(datos.get('total', 0))
    except (ValueError, TypeError):
        total = 0

    clase = str(datos.get('clase', 'Desconocido')).strip()

    try:
        conf = float(datos.get('conf', 0.0))
    except (ValueError, TypeError):
        conf = 0.0

    raw_enf = datos.get('enfermedad', False)
    if isinstance(raw_enf, str):
        enfermedad = raw_enf.strip().lower() in ['true', '1', 'yes', 't', 'si']
    else:
        enfermedad = bool(raw_enf)

    # Evaluación de la regla de persistencia
    if total > 0:
        consecutive_empty_count = 0
        debe_guardar_historial = True
    else:
        consecutive_empty_count += 1
        debe_guardar_historial = (consecutive_empty_count <= 4)

    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    fecha_hora_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if debe_guardar_historial:
        # Modo Persistencia: Crear archivo único y registrar en BD
        random_suffix = uuid.uuid4().hex[:6]
        orig_ext = os.path.splitext(secure_filename(file_storage.filename))[1]
        if not orig_ext or orig_ext.lower() not in ['.jpg', '.jpeg', '.png']:
            orig_ext = '.jpg'

        filename = f"{modelo}_{timestamp_str}_{random_suffix}{orig_ext}"
        file_path = os.path.join(UPLOADS_DIR, filename)

        try:
            file_storage.save(file_path)
        except Exception as e:
            return {"status": "error", "message": f"Error al guardar imagen en disco: {str(e)}"}, 500

        relative_path = f"uploads/detecciones/{filename}"

        try:
            new_id = d_detecciones.guardar_deteccion(
                path=relative_path,
                modelo=modelo,
                total=total,
                clase=clase,
                conf=conf,
                enfermedad=enfermedad
            )
        except Exception as e:
            return {"status": "error", "message": f"Error al insertar en la base de datos: {str(e)}"}, 500

        # Actualizar caché de visualización en vivo
        live_stream_cache = {
            "id": new_id,
            "path": relative_path,
            "image_url": f"/static/{relative_path}",
            "modelo": modelo,
            "total": total,
            "clase": clase,
            "conf": conf,
            "enfermedad": enfermedad,
            "fecha_hora": fecha_hora_str,
            "guardado_en_historial": True,
            "consecutive_empty": consecutive_empty_count
        }

        return {
            "status": "ok",
            "id": new_id,
            "path": relative_path,
            "image_url": f"/static/{relative_path}",
            "modelo": modelo,
            "total": total,
            "clase": clase,
            "conf": conf,
            "enfermedad": enfermedad,
            "guardado_en_historial": True
        }, 201

    else:
        # Modo En Vivo (Ahorro de Memoria):
        # Sobrescribe un único archivo temporal 'live_latest.jpg' sin ocupar espacio adicional
        live_filename = "live_latest.jpg"
        live_file_path = os.path.join(UPLOADS_DIR, live_filename)

        try:
            file_storage.save(live_file_path)
        except Exception as e:
            return {"status": "error", "message": f"Error al guardar fotograma en vivo: {str(e)}"}, 500

        relative_path = f"uploads/detecciones/{live_filename}"
        epoch_ts = int(datetime.now().timestamp() * 1000)
        image_url = f"/static/{relative_path}?t={epoch_ts}"

        live_stream_cache = {
            "id": "live_stream",
            "path": relative_path,
            "image_url": image_url,
            "modelo": modelo,
            "total": total,
            "clase": clase,
            "conf": conf,
            "enfermedad": enfermedad,
            "fecha_hora": fecha_hora_str,
            "guardado_en_historial": False,
            "consecutive_empty": consecutive_empty_count
        }

        return {
            "status": "ok",
            "id": None,
            "path": relative_path,
            "image_url": image_url,
            "modelo": modelo,
            "total": total,
            "clase": clase,
            "conf": conf,
            "enfermedad": enfermedad,
            "guardado_en_historial": False,
            "mensaje": f"En vivo activo: Sin guardar en disco ({consecutive_empty_count} envíos consecutivos sin detección)."
        }, 200

def obtener_ultima_deteccion():
    """
    Obtiene la detección más reciente para el panel en vivo.
    Verifica activamente si la Jetson Nano se encuentra conectada y enviando datos
    en los últimos 5 segundos.
    """
    global live_stream_cache, last_jetson_upload_time

    # Evaluar si la Jetson Nano está transmitiendo activamente (umbral de 8.0s)
    jetson_online = False
    segundos_desde_ultimo = None
    if last_jetson_upload_time is not None:
        segundos_desde_ultimo = round(time.time() - last_jetson_upload_time, 1)
        jetson_online = (segundos_desde_ultimo <= 8.0)

    if live_stream_cache:
        det = dict(live_stream_cache)
        det['jetson_online'] = jetson_online
        det['segundos_inactivo'] = segundos_desde_ultimo
        return {
            "status": "ok",
            "jetson_online": jetson_online,
            "segundos_desde_ultimo_envio": segundos_desde_ultimo,
            "deteccion": det
        }

    row = d_detecciones.obtener_ultima_deteccion()
    if not row:
        return {
            "status": "ok",
            "jetson_online": False,
            "segundos_desde_ultimo_envio": None,
            "deteccion": None
        }
    
    row['image_url'] = f"/static/{row['path']}"
    row['guardado_en_historial'] = True
    row['jetson_online'] = jetson_online
    row['segundos_inactivo'] = segundos_desde_ultimo
    return {
        "status": "ok",
        "jetson_online": jetson_online,
        "segundos_desde_ultimo_envio": segundos_desde_ultimo,
        "deteccion": row
    }


def obtener_historial_detecciones(limit=50):
    """
    Obtiene el historial de detecciones más recientes.
    """
    rows = d_detecciones.obtener_historial_detecciones(limit=limit)
    for r in rows:
        r['image_url'] = f"/static/{r['path']}"
    return {"status": "ok", "detecciones": rows, "total": len(rows)}

