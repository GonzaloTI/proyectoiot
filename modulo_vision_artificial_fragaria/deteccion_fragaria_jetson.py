import cv2
import numpy as np
import time
import os
import sys
import ctypes
import json
import queue
from threading import Thread

try:
    import requests
except ImportError:
    requests = None

# ==============================================================================
# CONEXIÓN SERIAL UART CON EL ESP32 (P3541 JETSON NANO)
# Pines: Pin 8 (TXD) -> ESP32 RX2 (GPIO 16) | Pin 10 (RXD) -> ESP32 TX2 (GPIO 17)
# ==============================================================================
try:
    import serial
    PUERTOS_SERIAL = [
        '/dev/ttyTHS1',  # UART en conector J41 (Pines 8 y 10) de la Jetson Nano
        '/dev/ttyUSB0',  # Conexión por cable USB
        '/dev/ttyACM0',
        'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8'
    ]
    esp32_serial = None
    for p in PUERTOS_SERIAL:
        try:
            esp32_serial = serial.Serial(p, 115200, timeout=0.05)
            print(f"[SERIAL] Conectado exitosamente al ESP32 en {p}")
            break
        except Exception:
            pass
    if not esp32_serial:
        print("[SERIAL] ESP32 no detectado en puertos estándar. Funcionando en modo local.")
except ImportError:
    esp32_serial = None
    print("[SERIAL] Módulo 'pyserial' no instalado. Funcionando solo en modo local.")

# ==============================================================================
# CONFIGURACIÓN GENERAL PARA JETSON NANO
# ==============================================================================
ENGINE_PATH = "best_fragaria2.engine"  # Nombre de tu motor TensorRT
IMGSZ = 640                          # Tamaño con el que se compiló el .engine (640 o 416)
CONF_THRES = 0.50                    # Umbral de confianza mínimo (50%)
IOU_THRES = 0.45                     # Umbral NMS para descartar cajas solapadas

# Selección y resolución de la cámara:
USAR_CAMARA_CSI = False              # True = Cámara Ribbon CSI (ej. Raspberry Pi v2 / IMX219)
INDICE_CAMARA_USB = 0                # 0 = Cámara USB (/dev/video0)
ANCHO_CAMARA = 640                   # Captura directa en 640x480 para eliminar el cuello de botella
ALTO_CAMARA = 480

# Nombres de las clases según data.yaml
NOMBRES_CLASES = [
    'Podredumbre de cuero',
    'Mancha negra (Antracnosis)',
    'Moho gris',
    'Oído',
    'Fruta sana'
]

# Paleta de colores vivos y contrastados (BGR)
COLORES = [
    (0, 0, 230),     # Podredumbre: Rojo intenso
    (0, 140, 255),   # Antracnosis: Naranja brillante
    (200, 0, 200),   # Moho gris: Magenta / Púrpura
    (255, 220, 0),   # Oído: Amarillo brillante
    (0, 220, 0),     # Fruta sana: Verde brillante
]

# ==============================================================================
# CONFIGURACIÓN DE TRANSMISIÓN WEB A FLASK (RENDER / RED LOCAL)
# ==============================================================================
SERVER_URL = "https://proyectoiot-l4mo.onrender.com"  # Servidor Flask en Render
TRANSMITIR_A_SERVIDOR = True
INTERVALO_SUBIDA_WEB_SEG = 1.5  # Subir máximo 1 fotograma cada 1.5s para no saturar

class SubidorDeteccionesWeb:
    """
    Hilo secundario asíncrono para subir imágenes y telemetría de detección al servidor Flask
    sin reducir los FPS del bucle principal de inferencia TensorRT.
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
            print(f"[WEB] Transmisión asíncrona a {self.server_url} activada.")
        else:
            if requests is None:
                print("[WEB] Advertencia: Módulo 'requests' no disponible. Subida web desactivada.")

    def encolar(self, jpeg_bytes, payload):
        if not self.enabled or not self.activo:
            return
        # Descartar fotogramas no procesados para siempre enviar el más reciente
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
                if resp.status_code == 201:
                    self.ultimo_exito = True
                else:
                    self.ultimo_exito = False
            except Exception:
                self.ultimo_exito = False
            finally:
                self.cola.task_done()

    def detener(self):
        self.activo = False

# ==============================================================================
# CAPTURA ASÍNCRONA DE CÁMARA (CLAVE PARA SUBIR A 20 FPS)
# Lee los fotogramas en un hilo secundario en paralelo con la GPU
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
            # Acelerar cámara USB con códec MJPG directo a 640x480
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
# NMS ULTRA-RÁPIDO EN NUMPY PURO
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

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h

        union = areas[i] + areas[order[1:]] - inter
        iou = inter / np.maximum(union, 1e-6)

        inds = np.where(iou <= iou_threshold)[0]
        order = order[inds + 1]

    return keep

# ==============================================================================
# DIBUJO DE DETECCIONES DE ALTA VISIBILIDAD
# ==============================================================================
def dibujar_deteccion(frame, x1, y1, x2, y2, clase_id, conf):
    color = COLORES[clase_id % len(COLORES)]
    nombre = NOMBRES_CLASES[clase_id] if clase_id < len(NOMBRES_CLASES) else f"Clase {clase_id}"

    # Bounding box
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    # Esquinas reforzadas
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

    # Etiqueta con fondo sólido
    texto = f"{nombre} {int(conf * 100)}%"
    font = cv2.FONT_HERSHEY_SIMPLEX
    escala = 0.55
    (tw, th), _ = cv2.getTextSize(texto, font, escala, 2)

    y_label = y1 - 8 if y1 - th - 10 > 0 else y1 + th + 12
    cv2.rectangle(frame, (x1, y_label - th - 6), (x1 + tw + 8, y_label + 2), color, -1)
    cv2.putText(frame, texto, (x1 + 4, y_label - 4), font, escala, (255, 255, 255), 2, cv2.LINE_AA)

# ==============================================================================
# MOTOR TENSORRT NATIVO (OPTIMIZADO CON BUFFERS PRE-ASIGNADOS)
# ==============================================================================
class TensorRTInference:
    def __init__(self, engine_path, imgsz=640):
        import tensorrt as trt

        self.imgsz = imgsz
        self.scale_factor = np.float32(1.0 / 255.0)  # Multiplicación rápida en vez de división
        self.logger = trt.Logger(trt.Logger.WARNING)

        try:
            self.cudart = ctypes.CDLL("libcudart.so")
        except OSError:
            self.cudart = ctypes.CDLL("/usr/local/cuda/lib64/libcudart.so")

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
                # Buffer de entrada pre-asignado para evitar recolector de basura en el loop
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
        # Redimensionado rápido con interpolación lineal
        img_resized = cv2.resize(img_bgr, (self.imgsz, self.imgsz), interpolation=cv2.INTER_LINEAR)
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        
        # Multiplicación optimizada
        img_norm = img_rgb.astype(np.float32) * self.scale_factor
        img_chw = np.transpose(img_norm, (2, 0, 1))
        np.copyto(self.input_host[0], img_chw)
        return w, h

    def inferir(self, frame, conf_thres=0.5, iou_thres=0.45):
        orig_w, orig_h = self.preprocesar(frame)

        # 1. Copiar Host -> Device (GPU)
        self.cudaMemcpy(
            self.input_alloc['d_ptr'],
            self.input_host.ctypes.data_as(ctypes.c_void_p),
            self.input_alloc['nbytes'],
            self.cudaMemcpyHostToDevice
        )

        # 2. Inferencia en GPU
        self.context.execute_v2(self.bindings)

        # 3. Copiar Device -> Host (CPU)
        self.cudaMemcpy(
            self.host_output.ctypes.data_as(ctypes.c_void_p),
            self.output_alloc['d_ptr'],
            self.output_alloc['nbytes'],
            self.cudaMemcpyDeviceToHost
        )

        # 4. Decodificar salida YOLO
        output = self.host_output[0].T  # (8400, 4 + 5)
        boxes = output[:, :4]
        scores = output[:, 4:]

        class_ids = np.argmax(scores, axis=1)
        confidences = scores[np.arange(len(scores)), class_ids]

        mask = confidences >= conf_thres
        boxes = boxes[mask]
        confidences = confidences[mask]
        class_ids = class_ids[mask]

        if len(boxes) == 0:
            return []

        x_scale = orig_w / float(self.imgsz)
        y_scale = orig_h / float(self.imgsz)

        cx = boxes[:, 0] * x_scale
        cy = boxes[:, 1] * y_scale
        bw = boxes[:, 2] * x_scale
        bh = boxes[:, 3] * y_scale

        x1 = np.clip(cx - bw / 2.0, 0, orig_w).astype(np.float32)
        y1 = np.clip(cy - bh / 2.0, 0, orig_h).astype(np.float32)
        x2 = np.clip(cx + bw / 2.0, 0, orig_w).astype(np.float32)
        y2 = np.clip(cy + bh / 2.0, 0, orig_h).astype(np.float32)

        boxes_xyxy = np.column_stack([x1, y1, x2, y2])
        indices = nms_numpy(boxes_xyxy, confidences, iou_thres)

        detecciones = []
        for idx in indices:
            detecciones.append({
                'box': (int(x1[idx]), int(y1[idx]), int(x2[idx]), int(y2[idx])),
                'conf': float(confidences[idx]),
                'class_id': int(class_ids[idx])
            })
        return detecciones

    def __del__(self):
        if hasattr(self, 'cudaFree'):
            if self.input_alloc and 'd_ptr' in self.input_alloc:
                self.cudaFree(self.input_alloc['d_ptr'])
            if self.output_alloc and 'd_ptr' in self.output_alloc:
                self.cudaFree(self.output_alloc['d_ptr'])

# ==============================================================================
# BUCLE PRINCIPAL
# ==============================================================================
def main():
    if not os.path.exists(ENGINE_PATH):
        print(f"\n[ERROR] No se encontró el archivo '{ENGINE_PATH}'.")
        return

    print("=" * 60)
    print("🍓 DETECCIÓN EN TIEMPO REAL - NVIDIA JETSON NANO (ALTO RENDIMIENTO)")
    print("=" * 60)

    # 1. Cargar motor TensorRT
    print("[INFO] Cargando motor TensorRT en GPU...")
    try:
        model = TensorRTInference(ENGINE_PATH, imgsz=IMGSZ)
        print("[INFO] ¡Motor TensorRT listo y buffers asignados!")
    except Exception as e:
        print(f"[ERROR] No se pudo inicializar TensorRT: {e}")
        return

    # 2. Inicializar cámara en hilo asíncrono
    print("[INFO] Iniciando lector asíncrono de cámara...")
    camara = CamaraAsincrona(
        src=INDICE_CAMARA_USB,
        is_csi=USAR_CAMARA_CSI,
        width=ANCHO_CAMARA,
        height=ALTO_CAMARA
    ).start()

    time.sleep(1.0)  # Esperar a que la cámara inicialice el primer frame

    fps = 0
    contador_frames = 0
    tiempo_inicio = time.time()
    ultimo_envio_serial = 0
    ultimo_envio_web = 0

    # Inicializar subidor web asíncrono hacia Flask
    subidor_web = SubidorDeteccionesWeb(SERVER_URL, enabled=TRANSMITIR_A_SERVIDOR)

    print("[INFO] Sistema listo. Presiona la tecla 'ESC' o 'Q' para salir.\n")

    while True:
        frame = camara.read()
        if frame is None:
            continue

        # Inferencia y dibujo
        detecciones = model.inferir(frame, conf_thres=CONF_THRES, iou_thres=IOU_THRES)
        for det in detecciones:
            x1, y1, x2, y2 = det['box']
            dibujar_deteccion(frame, x1, y1, x2, y2, det['class_id'], det['conf'])

        # Cálculo de FPS en tiempo real
        contador_frames += 1
        tiempo_actual = time.time()
        if tiempo_actual - tiempo_inicio >= 1.0:
            fps = contador_frames / (tiempo_actual - tiempo_inicio)
            contador_frames = 0
            tiempo_inicio = time.time()

        # Resumen de detección de Fragaria para transmisión UART y Web
        if len(detecciones) > 0:
            detecciones_ordenadas = sorted(detecciones, key=lambda d: d['conf'], reverse=True)
            mejor = detecciones_ordenadas[0]
            nombre_clase = NOMBRES_CLASES[mejor['class_id']]
            confianza = float(mejor['conf'])
            es_enfermedad = (mejor['class_id'] != 4)  # 4 = 'Fruta sana', cualquier otra es patología
            total_dets = len(detecciones)
        else:
            nombre_clase = "Ninguna"
            confianza = 0.0
            es_enfermedad = False
            total_dets = 0

        # Payload estructurado de detección
        payload = {
            "modelo": "fragaria",
            "total": total_dets,
            "clase": nombre_clase,
            "conf": round(confianza, 2),
            "enfermedad": es_enfermedad
        }

        # 1. Enviar resultados al ESP32 por UART cada ~150ms
        if esp32_serial and (tiempo_actual - ultimo_envio_serial >= 0.15):
            ultimo_envio_serial = tiempo_actual
            linea = json.dumps(payload) + "\n"
            try:
                if esp32_serial.in_waiting > 0:
                    esp32_serial.reset_input_buffer()
                esp32_serial.write(linea.encode('utf-8'))
            except Exception:
                pass

        # 2. Enviar fotograma y telemetría a la Web Flask de manera asíncrona cada INTERVALO_SUBIDA_WEB_SEG
        if TRANSMITIR_A_SERVIDOR and (tiempo_actual - ultimo_envio_web >= INTERVALO_SUBIDA_WEB_SEG):
            ultimo_envio_web = tiempo_actual
            ret_jpg, jpeg_buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            if ret_jpg:
                subidor_web.encolar(jpeg_buf.tobytes(), payload)

        # Visualizador de FPS
        cv2.rectangle(frame, (10, 10), (145, 45), (0, 0, 0), -1)
        cv2.putText(frame, f"FPS: {fps:.1f}", (18, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)

        # Barra inferior de estado UART, Web y diagnóstico
        estado_uart = "UART: OK" if esp32_serial else "UART: OFF"
        estado_web = "WEB: OK" if subidor_web.ultimo_exito else ("WEB: ACTIVA" if TRANSMITIR_A_SERVIDOR else "WEB: OFF")
        cv2.rectangle(frame, (10, ALTO_CAMARA - 35), (ANCHO_CAMARA - 10, ALTO_CAMARA - 5), (20, 20, 30), -1)
        texto_uart = f"[{estado_uart} | {estado_web}] Dets: {total_dets} | {nombre_clase} ({int(confianza * 100)}%)"
        cv2.putText(frame, texto_uart, (18, ALTO_CAMARA - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 200), 1, cv2.LINE_AA)

        # Mostrar imagen
        cv2.imshow("DETECCION JETSON NANO (TENSORRT)", frame)

        tecla = cv2.waitKey(1) & 0xFF
        if tecla == 27 or tecla == ord('q'):
            break

    subidor_web.detener()
    camara.release()
    cv2.destroyAllWindows()
    if esp32_serial:
        esp32_serial.close()
    print("[INFO] Programa finalizado.")

if __name__ == "__main__":
    main()
