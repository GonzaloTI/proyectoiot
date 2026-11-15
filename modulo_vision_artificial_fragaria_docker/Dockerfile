# ==============================================================================
# Dockerfile para NVIDIA Jetson Nano (JetPack 4.6+ / L4T R32.7.x)
# Módulo de Visión Artificial - Fragaria (TensorRT + ESP32 UART + Web Stream)
# ==============================================================================

# Imagen base oficial de NVIDIA para Tegra aarch64 (L4T)
ARG L4T_VERSION=r32.7.1
FROM nvcr.io/nvidia/l4t-base:${L4T_VERSION}

# Evitar diálogos interactivos en la instalación de paquetes
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Instalar dependencias esenciales de Python, OpenCV y GStreamer
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    python3-numpy \
    python3-opencv \
    libgstreamer1.0-0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    v4l-utils \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo dentro del contenedor
WORKDIR /app

# Instalar dependencias de Python (pyserial, requests)
COPY requirements.txt /app/
RUN pip3 install --no-cache-dir -r requirements.txt

# Copiar el script principal de inferencia
COPY deteccion_fragaria_jetson.py /app/

# Variables de entorno por defecto (configurables en runtime o docker-compose)
ENV SERVER_URL="https://proyectoiot-l4mo.onrender.com"
ENV SERIAL_PORT="/dev/ttyTHS1"
ENV SERIAL_BAUD=115200
ENV CAMERA_INDEX=0
ENV USE_CSI_CAMERA="false"
ENV CONF_THRES=0.50
ENV IOU_THRES=0.45
ENV INTERVALO_SUBIDA_SEG=1.5
ENV HEADLESS="true"
ENV ENGINE_PATH="/app/best_fragaria2.engine"

# Ejecución del módulo
CMD ["python3", "deteccion_fragaria_jetson.py"]

