import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from modelos.Ddetecciones import Ddetecciones

# Directorio base para almacenamiento de imágenes de detecciones
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
UPLOADS_DIR = os.path.join(BASE_DIR, 'static', 'uploads', 'detecciones')
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Instancia del modelo de datos Ddetecciones
d_detecciones = Ddetecciones()

def procesar_subida_deteccion(file_storage, datos):
    """
    Procesa y guarda la imagen y metadatos de detección enviados por la Jetson Nano.
    
    Parámetros:
      file_storage: Objeto FileStorage de werkzeug (request.files['imagen'] o request.files['file'])
      datos: Diccionario con { "modelo": ..., "total": ..., "clase": ..., "conf": ..., "enfermedad": ... }
    
    Retorna:
      dict: Respuesta estructurada {"status": "ok", "id": ..., "path": ...} o error.
    """
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

    # Generar un nombre único para la imagen
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
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

    # Ruta relativa dentro de la carpeta static para ser accesible web
    relative_path = f"uploads/detecciones/{filename}"

    # Guardar registro en la base de datos
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

    return {
        "status": "ok",
        "id": new_id,
        "path": relative_path,
        "image_url": f"/static/{relative_path}",
        "modelo": modelo,
        "total": total,
        "clase": clase,
        "conf": conf,
        "enfermedad": enfermedad
    }, 201

def obtener_ultima_deteccion():
    """
    Obtiene la detección más reciente registrada en el sistema.
    """
    row = d_detecciones.obtener_ultima_deteccion()
    if not row:
        return {"status": "ok", "deteccion": None}
    
    # Agregar URL accesible para la plantilla HTML o llamada AJAX
    row['image_url'] = f"/static/{row['path']}"
    return {"status": "ok", "deteccion": row}

def obtener_historial_detecciones(limit=50):
    """
    Obtiene el historial de detecciones más recientes.
    """
    rows = d_detecciones.obtener_historial_detecciones(limit=limit)
    for r in rows:
        r['image_url'] = f"/static/{r['path']}"
    return {"status": "ok", "detecciones": rows, "total": len(rows)}

