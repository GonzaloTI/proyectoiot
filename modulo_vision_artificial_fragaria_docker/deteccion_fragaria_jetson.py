import cv2
import numpy as np
import time
import os
import sys
import ctypes
import json
import queue
import signal
from threading import Thread

# Asegurar codificación robusta en stdout para Docker
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

try:
    import requests
except ImportError:
    requests = None

# ==============================================================================
# CONFIGURACIÓN GENERAL (VARIABLES DE ENTORNO O VALORES POR DEFECTO)
# ==============================================================================
ENGINE_PATH = os.environ.get("ENGINE_PATH", "best_fragaria2.engine")
SERVER_URL = os.environ.get("SERVER_URL", "https://proyectoiot-l4mo.onrender.com")
SERIAL_PORT = os.environ.get("SERIAL_PORT", "/dev/ttyTHS1")
SERIAL_BAUD = int(os.environ.get("SERIAL_BAUD", "115200"))
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
USE_CSI_CAMERA = os.environ.get("USE_CSI_CAMERA", "false").lower() in ("true", "1", "yes")
CONF_THRES = float(os.environ.get("CONF_THRES", "0.50"))
IOU_THRES = float(os.environ.get("IOU_THRES", "0.45"))
INTERVALO_SUBIDA_WEB_SEG = float(os.environ.get("INTERVALO_SUBIDA_SEG", "1.5"))
HEADLESS = os.environ.get("HEADLESS", "true").lower() in ("true", "1", "yes")
TRANSMITIR_A_SERVIDOR = True

IMGSZ = 640
ANCHO_CAMARA = 640
ALTO_CAMARA = 480

# Control de ejecución y parada limpia (compatible con 'docker stop')
ejecutando = True

def handle_signal(sig, frame):
    global ejecutando
    print(f"\n[INFO] Senal de apagado recibida ({sig}). Finalizando detector de forma ordenada...")
    ejecutando = False

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

# ==============================================================================
# CONEXIÓN SERIAL UART CON EL ESP32
# ==============================================================================
esp32_serial = None
try:
    import serial
    puertos_a_probar = [SERIAL_PORT]
    # Si falla el puerto configurado, probar alternativas estándar
    for alt in ['/dev/ttyTHS1', '/dev/ttyUSB0', '/dev/ttyACM0']:
        if alt not in puertos_a_probar:
            puertos_a_probar.append(alt)

    for p in puertos_a_probar:
        try:
            esp32_serial = serial.Serial(p, SERIAL_BAUD, timeout=0.05)
            print(f"[SERIAL] Conectado exitosamente al ESP32 en {p} ({SERIAL_BAUD} baud)")
            break
        except Exception:
            pass
    if not esp32_serial:
        print(f"[SERIAL] Advertencia: No se pudo abrir {SERIAL_PORT}. Funcionando en modo local.")
except ImportError:
    print("[SERIAL] Advertencia: Modulo 'pyserial' no instalado. Comunicacion UART desactivada.")

# ==============================================================================
# CLASES Y COLORES DEL MODELO FRAGARIA
# ==============================================================================
NOMBRES_CLASES = [
    'Podredumbre de cuero',
    'Mancha negra (Antracnosis)',
    'Moho gris',
    'Oído',
    'Fruta sana'
]

COLORES = [
    (0, 0, 230),     # Podredumbre: Rojo intenso
    (0, 140, 255),   # Antracnosis: Naranja brillante
    (200, 0, 200),   # Moho gris: Magenta / Púrpura
    (255, 220, 0),   # Oído: Amarillo brillante
    (0, 220, 0),     # Fruta sana: Verde brillante
]

# ==============================================================================
# HILO ASÍNCRONO DE SUBIDA WEB HACIA FLASK
# ==============================================================================
class SubidorDeteccionesWeb:
    """
    Sube fotogramas con diagnóstico al servidor Flask en segundo plano.
    Garantiza 0 ms de bloqueo en el bucle principal de inferencia TensorRT.
    """
    def __init__(self, server_url, enabled=True):
        self.server_url = server_url.rstrip('/')
        self.enabled = enabled and (requests is not None)
        self.cola = queue.Queue(maxsize=1)
        self.activo = True
        self.ultimo_exito = False
        if self.enabled:
            self.hilo = Thread(target=self._worker, daemon=True)
            self.hilo.start()
            print(f"[WEB] Transmision asincrona hacia {self.server_url} activada.")
        else:
            if requests is None:
                print("[WEB] Advertencia: Modulo 'requests' no disponible. Subida web desactivada.")

    def encolar(self, jpeg_bytes, payload):
        if not self.enabled or not self.activo:
            return
        if self.cola.full():
            try:
                self.cola.get_nowait()
            except queue.Empty:
                pass
        try:
            self.cola.put_nowait((jpeg_bytes, payload))
        except queue.Full:
            pass

    def _worker(self):
        while self.activo:
            try:
                item = self.cola.get(timeout=1.0)
            except queue.Empty:
                continue

            jpeg_bytes, payload = item
            try:
                files = {
                    'imagen': ('captura_jetson.jpg', jpeg_bytes, 'image/jpeg')
                }
                data = {
                    'modelo': str(payload.get('modelo', 'fragaria')),
                    'total': str(payload.get('total', 0)),
                    'clase': str(payload.get('clase', '')),
                    'conf': str(payload.get('conf', 0.0)),
                    'enfermedad': 'true' if payload.get('enfermedad', False) else 'false'
                }
                url = f"{self.server_url}/api/detecciones/subir"
                resp = requests.post(url, files=files, data=data, timeout=4.0)
                self.ultimo_exito = (resp.status_code in [200, 201])
            except Exception:
                self.ultimo_exito = False
            finally:
                self.cola.task_done()

    def detener(self):
        self.activo = False

# ==============================================================================
# CAPTURA ASÍNCRONA DE CÁMARA (V4L2 / GStreamer)
# ==============================================================================
class CamaraAsincrona:
    def __init__(self, src=0, is_csi=False, width=640, height=480):
        self.is_csi = is_csi
        if is_csi:
            pipeline = (
                f"nvarguscamerasrc sensor-id={src} ! "
                f"video/x-raw(memory:NVMM), width=(int){width}, height=(int){height}, "
                f"format=(string)NV12, framerate=(fraction)30/1 ! "
                f"nvvidconv flip-method=0 ! "
                f"video/x-raw, width=(int){width}, height=(int){height}, format=(string)BGRx ! "
                f"videoconvert ! "
                f"video/x-raw, format=(string)BGR ! appsink drop=true"
            )
            self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            self.cap = cv2.VideoCapture(src)
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.cap.set(cv2.CAP_PROP_FPS, 30)

        self.ret, self.frame = self.cap.read()
        self.detenido = False

    def start(self):
        self.hilo = Thread(target=self._actualizar, daemon=True)
        self.hilo.start()
        return self

    def _actualizar(self):
        while not self.detenido:
            ret, frame = self.cap.read()
            if ret:
                self.frame = frame
            else:
                self.detenido = True

    def read(self):
        return self.frame

    def release(self):
        self.detenido = True
        self.cap.release()

# ==============================================================================
# NMS ULTRA-RÁPIDO EN NUMPY
# ==============================================================================
def nms_numpy(boxes, scores, iou_threshold=0.45):
    if len(boxes) == 0:
        return []

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]

    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []

    while order.size > 0:
        i = order[0]
        keep.append(i)
        if order.size == 1:
            break

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h

        ovr = inter / (areas[i] + areas[order[1:]] - inter)
        inds = np.where(ovr <= iou_threshold)[0]
        order = order[inds + 1]

    return keep

# ==============================================================================
# DIBUJO DE DETECCIONES
# ==============================================================================
def dibujar_deteccion(frame, x1, y1, x2, y2, clase_id, conf):
    color = COLORES[clase_id % len(COLORES)]
    nombre = NOMBRES_CLASES[clase_id] if clase_id < len(NOMBRES_CLASES) else f"Clase {clase_id}"

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    len_esq = max(10, int(min(x2 - x1, y2 - y1) * 0.15))
    grosor_esq = 4
    cv2.line(frame, (x1, y1), (x1 + len_esq, y1), color, grosor_esq)
    cv2.line(frame, (x1, y1), (x1, y1 + len_esq), color, grosor_esq)
    cv2.line(frame, (x2, y1), (x2 - len_esq, y1), color, grosor_esq)
    cv2.line(frame, (x2, y1), (x2, y1 + len_esq), color, grosor_esq)
    cv2.line(frame, (x1, y2), (x1 + len_esq, y2), color, grosor_esq)
    cv2.line(frame, (x1, y2), (x1, y2 - len_esq), color, grosor_esq)
    cv2.line(frame, (x2, y2), (x2 - len_esq, y2), color, grosor_esq)
    cv2.line(frame, (x2, y2), (x2, y2 - len_esq), color, grosor_esq)

    texto = f"{nombre} {int(conf * 100)}%"
    font = cv2.FONT_HERSHEY_SIMPLEX
    escala = 0.55
    (tw, th), _ = cv2.getTextSize(texto, font, escala, 2)

    y_label = y1 - 8 if y1 - th - 10 > 0 else y1 + th + 12
    cv2.rectangle(frame, (x1, y_label - th - 6), (x1 + tw + 8, y_label + 2), color, -1)
    cv2.putText(frame, texto, (x1 + 4, y_label - 4), font, escala, (255, 255, 255), 2, cv2.LINE_AA)

# ==============================================================================
# MOTOR TENSORRT NATIVO (BUFFERS PRE-ASIGNADOS EN GPU)
# ==============================================================================
class TensorRTInference:
    def __init__(self, engine_path, imgsz=640):
        import tensorrt as trt

        self.imgsz = imgsz
        self.scale_factor = np.float32(1.0 / 255.0)
        self.logger = trt.Logger(trt.Logger.WARNING)

        rutas_cudart = [
            "libcudart.so",
            "/usr/local/cuda/lib64/libcudart.so",
            "/usr/lib/aarch64-linux-gnu/libcudart.so"
        ]
        self.cudart = None
        for ruta in rutas_cudart:
            try:
                self.cudart = ctypes.CDLL(ruta)
                break
            except OSError:
                pass
        if not self.cudart:
            raise RuntimeError("No se pudo localizar 'libcudart.so' en el sistema/contenedor.")

        self.cudaMalloc = self.cudart.cudaMalloc
        self.cudaMalloc.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t]
        self.cudaMalloc.restype = ctypes.c_int

        self.cudaMemcpy = self.cudart.cudaMemcpy
        self.cudaMemcpy.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
        self.cudaMemcpy.restype = ctypes.c_int

        self.cudaFree = self.cudart.cudaFree
        self.cudaFree.argtypes = [ctypes.c_void_p]
        self.cudaFree.restype = ctypes.c_int

        self.cudaMemcpyHostToDevice = 1
        self.cudaMemcpyDeviceToHost = 2

        if not os.path.exists(engine_path):
            raise FileNotFoundError(f"Archivo de motor TensorRT no encontrado: {engine_path}")

        with open(engine_path, "rb") as f, trt.Runtime(self.logger) as runtime:
            self.engine = runtime.deserialize_cuda_engine(f.read())

        self.context = self.engine.create_execution_context()
        self.bindings = []
        self.input_alloc = {}
        self.output_alloc = {}

        for binding in self.engine:
            shape = self.engine.get_binding_shape(binding)
            size = trt.volume(shape)
            dtype = trt.nptype(self.engine.get_binding_dtype(binding))
            nbytes = int(size * np.dtype(dtype).itemsize)

            d_ptr = ctypes.c_void_p()
            status = self.cudaMalloc(ctypes.byref(d_ptr), nbytes)
            if status != 0:
                raise RuntimeError(f"Error asignando memoria CUDA (código: {status})")

            self.bindings.append(int(d_ptr.value))

            if self.engine.binding_is_input(binding):
                self.input_alloc = {
                    'd_ptr': d_ptr,
                    'nbytes': nbytes,
                    'shape': shape,
                    'dtype': dtype
                }
                self.input_host = np.empty(shape, dtype=dtype)
            else:
                self.output_alloc = {
                    'd_ptr': d_ptr,
                    'nbytes': nbytes,
                    'shape': shape,
                    'dtype': dtype
                }
                self.host_output = np.empty(shape, dtype=dtype)

    def preprocesar(self, img_bgr):
        h, w = img_bgr.shape[:2]
        img_resized = cv2.resize(img_bgr, (self.imgsz, self.imgsz), interpolation=cv2.INTER_LINEAR)
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        img_norm = img_rgb.astype(np.float32) * self.scale_factor
        img_chw = np.transpose(img_norm, (2, 0, 1))
        np.copyto(self.input_host[0], img_chw)
        return w, h

    def inferir(self, frame, conf_thres=0.5, iou_thres=0.45):
        orig_w, orig_h = self.preprocesar(frame)

        self.cudaMemcpy(
            self.input_alloc['d_ptr'],
            self.input_host.ctypes.data_as(ctypes.c_void_p),
            self.input_alloc['nbytes'],
            self.cudaMemcpyHostToDevice
        )

        self.context.execute_v2(self.bindings)

        self.cudaMemcpy(
            self.host_output.ctypes.data_as(ctypes.c_void_p),
            self.output_alloc['d_ptr'],
            self.output_alloc['nbytes'],
            self.cudaMemcpyDeviceToHost
        )

        salida = self.host_output[0]
        if salida.shape[0] < salida.shape[1]:
            salida = salida.T

        boxes_cxcywh = salida[:, :4]
        class_scores = salida[:, 4:]

        max_scores = np.max(class_scores, axis=1)
        class_ids = np.argmax(class_scores, axis=1)

        mask = max_scores >= conf_thres
        if not np.any(mask):
            return []

        filtrados_cxcywh = boxes_cxcywh[mask]
        filtrados_scores = max_scores[mask]
        filtrados_classes = class_ids[mask]

        cx = filtrados_cxcywh[:, 0]
        cy = filtrados_cxcywh[:, 1]
        bw = filtrados_cxcywh[:, 2]
        bh = filtrados_cxcywh[:, 3]

        scale_x = orig_w / float(self.imgsz)
        scale_y = orig_h / float(self.imgsz)

        x1 = np.clip((cx - bw / 2.0) * scale_x, 0, orig_w).astype(np.int32)
        y1 = np.clip((cy - bh / 2.0) * scale_y, 0, orig_h).astype(np.int32)
        x2 = np.clip((cx + bw / 2.0) * scale_x, 0, orig_w).astype(np.int32)
        y2 = np.clip((cy + bh / 2.0) * scale_y, 0, orig_h).astype(np.int32)

        cajas_xyxy = np.column_stack((x1, y1, x2, y2))
        indices_keep = nms_numpy(cajas_xyxy, filtrados_scores, iou_threshold=iou_thres)

        detecciones = []
        for i in indices_keep:
            detecciones.append({
                'box': (int(x1[i]), int(y1[i]), int(x2[i]), int(y2[i])),
                'conf': float(filtrados_scores[i]),
                'class_id': int(filtrados_classes[i])
            })

        return detecciones

# ==============================================================================
# FUNCIÓN PRINCIPAL
# ==============================================================================
def main():
    global ejecutando
    print("=" * 65)
    print("[INICIO] INICIANDO MODULO FRAGARIA EN JETSON NANO (DOCKER / TENSORRT)")
    print(f"   - Motor TensorRT : {ENGINE_PATH}")
    print(f"   - Servidor Flask : {SERVER_URL}")
    print(f"   - Puerto Serial  : {SERIAL_PORT}")
    print(f"   - Camara         : {'CSI' if USE_CSI_CAMERA else f'USB Index {CAMERA_INDEX}'}")
    print(f"   - Modo Headless  : {'ACTIVADO (Sin ventana GUI)' if HEADLESS else 'DESACTIVADO (Ventana X11)'}")
    print(f"   - Umbral Conf    : {CONF_THRES * 100:.0f}%")
    print("=" * 65)

    # 1. Cargar motor TensorRT
    print("[INFO] Cargando motor TensorRT en GPU...")
    try:
        model = TensorRTInference(ENGINE_PATH, imgsz=IMGSZ)
        print("[INFO] Motor TensorRT listo y buffers asignados en GPU!")
    except Exception as e:
        print(f"[ERROR CRITICO] No se pudo inicializar TensorRT: {e}")
        return

    # 2. Inicializar cámara en hilo asíncrono
    print("[INFO] Iniciando lector asincrono de camara...")
    camara = CamaraAsincrona(
        src=CAMERA_INDEX,
        is_csi=USE_CSI_CAMERA,
        width=ANCHO_CAMARA,
        height=ALTO_CAMARA
    ).start()

    time.sleep(1.0)

    fps = 0.0
    contador_frames = 0
    tiempo_inicio = time.time()
    ultimo_envio_serial = 0
    ultimo_envio_web = 0
    ultimo_log_consola = 0

    subidor_web = SubidorDeteccionesWeb(SERVER_URL, enabled=TRANSMITIR_A_SERVIDOR)
    print("[INFO] Detector en ejecucion activa. Esperando fotogramas...\n")

    while ejecutando:
        frame = camara.read()
        if frame is None:
            time.sleep(0.01)
            continue

        # Inferencia con GPU
        detecciones = model.inferir(frame, conf_thres=CONF_THRES, iou_thres=IOU_THRES)
        for det in detecciones:
            x1, y1, x2, y2 = det['box']
            dibujar_deteccion(frame, x1, y1, x2, y2, det['class_id'], det['conf'])

        # Cálculo de FPS
        contador_frames += 1
        tiempo_actual = time.time()
        if tiempo_actual - tiempo_inicio >= 1.0:
            fps = contador_frames / (tiempo_actual - tiempo_inicio)
            contador_frames = 0
            tiempo_inicio = time.time()

        # Resumen de detección
        if len(detecciones) > 0:
            detecciones_ordenadas = sorted(detecciones, key=lambda d: d['conf'], reverse=True)
            mejor = detecciones_ordenadas[0]
            nombre_clase = NOMBRES_CLASES[mejor['class_id']]
            confianza = float(mejor['conf'])
            es_enfermedad = (mejor['class_id'] != 4)
            total_dets = len(detecciones)
        else:
            nombre_clase = "Ninguna"
            confianza = 0.0
            es_enfermedad = False
            total_dets = 0

        payload = {
            "modelo": "fragaria",
            "total": total_dets,
            "clase": nombre_clase,
            "conf": round(confianza, 2),
            "enfermedad": es_enfermedad
        }

        # 1. Enviar telemetría al ESP32 por UART (~150ms)
        if esp32_serial and (tiempo_actual - ultimo_envio_serial >= 0.15):
            ultimo_envio_serial = tiempo_actual
            linea = json.dumps(payload) + "\n"
            try:
                if esp32_serial.in_waiting > 0:
                    esp32_serial.reset_input_buffer()
                esp32_serial.write(linea.encode('utf-8'))
            except Exception:
                pass

        # 2. Enviar fotograma y telemetría a Flask para la interfaz Web
        if TRANSMITIR_A_SERVIDOR and (tiempo_actual - ultimo_envio_web >= INTERVALO_SUBIDA_WEB_SEG):
            ultimo_envio_web = tiempo_actual
            ret_jpg, jpeg_buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            if ret_jpg:
                subidor_web.encolar(jpeg_buf.tobytes(), payload)

        # 3. Log periódico en consola (cada 2.5s) para monitorización en Docker Logs
        if tiempo_actual - ultimo_log_consola >= 2.5:
            ultimo_log_consola = tiempo_actual
            estado_uart = "OK" if esp32_serial else "OFF"
            estado_web = "OK" if subidor_web.ultimo_exito else ("ON" if TRANSMITIR_A_SERVIDOR else "OFF")
            diag_str = f"{nombre_clase} ({int(confianza * 100)}%)" if total_dets > 0 else "Sin objetos"
            print(f"[MONITOR] FPS: {fps:.1f} | UART: {estado_uart} | Web: {estado_web} | Dets: {total_dets} | {diag_str}")

        # 4. Modo gráfico (solo si no es Headless)
        if not HEADLESS:
            cv2.rectangle(frame, (10, 10), (145, 45), (0, 0, 0), -1)
            cv2.putText(frame, f"FPS: {fps:.1f}", (18, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow("DETECCION JETSON NANO (TENSORRT)", frame)
            tecla = cv2.waitKey(1) & 0xFF
            if tecla == 27 or tecla == ord('q'):
                break
        else:
            # Pequeña pausa para no saturar si no hay espera por GUI
            time.sleep(0.001)

    print("\n[INFO] Cerrando recursos...")
    subidor_web.detener()
    camara.release()
    if not HEADLESS:
        cv2.destroyAllWindows()
    if esp32_serial:
        esp32_serial.close()
    print("[INFO] Modulo detenido correctamente.")

if __name__ == "__main__":
    main()

