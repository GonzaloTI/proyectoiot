# 🍓 Módulo de Visión Artificial Fragaria en Docker (NVIDIA Jetson Nano)

Este módulo empaqueta el sistema completo de inferencia con **TensorRT**, transmisión **UART al ESP32** y streaming en vivo hacia el **Servidor Web Flask** dentro de un contenedor Docker optimizado para la plataforma NVIDIA Jetson.

---

## 🚀 Ventajas de esta versión Docker

1. **Sin ventana gráfica (Modo Headless):** No consume memoria RAM ni GPU abriendo ventanas X11/HDMI en la Jetson, ya que la visualización se transmite directamente a la interfaz web.
2. **Arranque automático:** Configurado con `--restart unless-stopped`, por lo que se inicia automáticamente cada vez que la Jetson Nano se enciende o reinicia.
3. **Aceleración GPU pura:** Utiliza el runtime oficial de NVIDIA (`--runtime nvidia`) para ejecutar el motor `.engine` a máxima velocidad (20-25 FPS).
4. **Actualización del modelo sin reconstruir:** El archivo `best_fragaria2.engine` se monta como volumen externo. Si reentrenas el modelo, solo reemplazas el archivo en la carpeta.

---

## 📁 Archivos en este Módulo

- `Dockerfile`: Imagen base NVIDIA L4T con soporte para TensorRT, CUDA, OpenCV y Python 3.
- `docker-compose.yml`: Orquestación del servicio con paso de GPU, cámara `/dev/video0` y puerto serial `/dev/ttyTHS1`.
- `deteccion_fragaria_jetson.py`: Script de inferencia TensorRT optimizado para contenedores, con manejo de señales (`SIGTERM`) y monitor en consola.
- `build.sh`: Script para compilar la imagen Docker en la Jetson.
- `run.sh`: Script para iniciar el contenedor en segundo plano con todos los permisos necesarios.
- `stop.sh`: Script para detener y remover el contenedor.
- `requirements.txt`: Dependencias de Python (`pyserial`, `requests`).
- `arduino_con_jetson_fragaria.ino`: Firmware para el microcontrolador ESP32.

---

## 🛠️ Instrucciones de Instalación en la Jetson Nano

### Paso 1: Copiar la carpeta a la Jetson Nano
Copia la carpeta `modulo_vision_artificial_fragaria_docker` a tu Jetson Nano (por ejemplo, en `~/modulo_vision_artificial_fragaria_docker`).

### Paso 2: Colocar el motor TensorRT
Asegúrate de que tu archivo de motor `best_fragaria2.engine` esté dentro de esta misma carpeta:
```bash
cd ~/modulo_vision_artificial_fragaria_docker
ls -lh best_fragaria2.engine
```

### Paso 3: Dar permisos de ejecución a los scripts
```bash
chmod +x build.sh run.sh stop.sh
```

### Paso 4: Construir la imagen Docker (Solo la primera vez)
```bash
./build.sh
```
*(O alternativamente: `docker-compose build`)*

### Paso 5: Iniciar el contenedor
```bash
./run.sh
```
*(O alternativamente con Docker Compose: `docker-compose up -d`)*

---

## 📊 Monitoreo y Verificación

Para ver la telemetría, FPS y diagnósticos en tiempo real generados por el contenedor:
```bash
docker logs -f fragaria_detector
```

Verás una salida similar a:
```text
🍓 INICIANDO MÓDULO FRAGARIA EN JETSON NANO (DOCKER / TENSORRT)
   - Motor TensorRT : /app/best_fragaria2.engine
   - Servidor Flask : https://proyectoiot-l4mo.onrender.com
   - Puerto Serial  : /dev/ttyTHS1
   - Modo Headless  : ACTIVADO (Sin ventana GUI)
[INFO] ¡Motor TensorRT listo y buffers asignados en GPU!
[INFO] Conectado exitosamente al ESP32 en /dev/ttyTHS1 (115200 baud)
[WEB] Transmisión asíncrona hacia https://proyectoiot-l4mo.onrender.com activada.
[MONITOR] FPS: 23.1 | UART: OK | Web: OK | Dets: 1 | Fruta sana (89%)
[MONITOR] FPS: 22.8 | UART: OK | Web: OK | Dets: 1 | Fruta sana (91%)
```

Para detener el contenedor en cualquier momento:
```bash
./stop.sh
```

---

## 🔌 Conexión Física de Pines (Jetson Nano <---> ESP32)

| NVIDIA Jetson Nano (J41 40-Pines) | ESP32 WROOM / DevKit | Función |
| :--- | :--- | :--- |
| **Pin 8 (UART2 TXD / GPIO 14)** | **GPIO 16 (RX2)** | Jetson transmite diagnóstico a ESP32 |
| **Pin 10 (UART2 RXD / GPIO 15)** | **GPIO 17 (TX2)** | ESP32 responde a Jetson |
| **Pin 6, 9 o 14 (GND)** | **GND** | Tierra común de referencia |

> [!NOTE]
> Si en lugar de los pines GPIO conectas el ESP32 por cable USB a la Jetson Nano, el puerto pasará a ser `/dev/ttyUSB0`. En `run.sh` o `docker-compose.yml`, cambia `SERIAL_PORT=/dev/ttyUSB0` y descomenta el dispositivo correspondiente.

