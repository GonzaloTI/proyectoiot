#!/bin/bash
# ==============================================================================
# Script para detener el contenedor de detección en NVIDIA Jetson Nano
# ==============================================================================
CONTAINER_NAME="fragaria_detector"

echo "🛑 Deteniendo contenedor '${CONTAINER_NAME}'..."
docker stop ${CONTAINER_NAME} 2>/dev/null || true
docker rm ${CONTAINER_NAME} 2>/dev/null || true

echo "✅ Contenedor detenido y liberado."

