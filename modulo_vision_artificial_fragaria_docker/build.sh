#!/bin/bash
# ==============================================================================
# Script de construcción de la imagen Docker en NVIDIA Jetson Nano
# ==============================================================================
set -e

echo "🔨 Construyendo imagen Docker para Fragaria Detector..."
docker build -t fragaria-detector:latest .

echo "✅ Imagen 'fragaria-detector:latest' construida exitosamente."

