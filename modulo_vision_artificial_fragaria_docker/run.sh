#!/bin/bash
# ==============================================================================
# Script para iniciar el contenedor de detección en NVIDIA Jetson Nano
# ==============================================================================
set -e

CONTAINER_NAME="fragaria_detector"
IMAGE_NAME="fragaria-detector:latest"
ENGINE_FILE="$(pwd)/best_fragaria2.engine"

# Verificar existencia del motor TensorRT
if [ ! -f "$ENGINE_FILE" ]; then
    echo "⚠️  ADVERTENCIA: No se encontró '$ENGINE_FILE' en el directorio actual."
    echo "   Asegúrate de copiar tu archivo 'best_fragaria2.engine' en esta carpeta antes de continuar."
fi

# Detener y remover contenedor previo si ya estaba corriendo
if [ $(docker ps -a -q -f name=^/${CONTAINER_NAME}$) ]; then
    echo "🛑 Deteniendo contenedor anterior..."
    docker stop ${CONTAINER_NAME} >/dev/null 2>&1 || true
    docker rm ${CONTAINER_NAME} >/dev/null 2>&1 || true
fi

# Detectar puerto UART disponible (/dev/ttyTHS1 pines 8/10 o /dev/ttyUSB0 cable)
SERIAL_DEV="/dev/ttyTHS1"
if [ ! -e "$SERIAL_DEV" ] && [ -e "/dev/ttyUSB0" ]; then
    SERIAL_DEV="/dev/ttyUSB0"
fi

DEVICE_FLAGS="--device /dev/video0:/dev/video0"
if [ -e "$SERIAL_DEV" ]; then
    DEVICE_FLAGS="$DEVICE_FLAGS --device $SERIAL_DEV:$SERIAL_DEV"
    echo "🔌 Puerto Serial detectado: $SERIAL_DEV"
else
    echo "⚠️  Puerto serial $SERIAL_DEV no encontrado. Corriendo en modo visual local."
fi

# Permisos para UART y Video
sudo chmod 666 /dev/video* 2>/dev/null || true
sudo chmod 666 /dev/ttyTHS* /dev/ttyUSB* 2>/dev/null || true

echo "🚀 Iniciando contenedor '${CONTAINER_NAME}' con NVIDIA Container Runtime..."

docker run -d \
    --name ${CONTAINER_NAME} \
    --runtime nvidia \
    --network host \
    --restart unless-stopped \
    $DEVICE_FLAGS \
    -v "$ENGINE_FILE":/app/best_fragaria2.engine \
    -e SERVER_URL="https://proyectoiot-l4mo.onrender.com" \
    -e SERIAL_PORT="$SERIAL_DEV" \
    -e HEADLESS="true" \
    -e INTERVALO_SUBIDA_SEG="1.5" \
    ${IMAGE_NAME}

echo "✅ Contenedor iniciado en segundo plano."
echo "📋 Para ver la telemetría y diagnósticos en tiempo real, ejecuta:"
echo "   docker logs -f ${CONTAINER_NAME}"

