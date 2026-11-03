"""
=============================================================================
  DETECTOR Y CONTADOR DE DEDOS EN VIVO CON MEDIAPIPE (JETSON NANO & ESP32)
=============================================================================
"""

import os
import sys
import time
import math
import argparse
import numpy as np

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

import cv2
import json
import mediapipe as mp

# Intento de conexión con ESP32 por UART / Serial
try:
    import serial
    # En Jetson Nano, Pin 8 (TX) y Pin 10 (RX) corresponden a /dev/ttyTHS1
    PUERTOS_SERIAL = [
        '/dev/ttyTHS1',
        '/dev/ttyUSB0',
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
        print("[SERIAL] ESP32 no detectado en puertos estándar. Funcionando en modo visual/simulación.")
except ImportError:
    esp32_serial = None
    print("[SERIAL] Módulo 'pyserial' no instalado. Funcionando solo en modo visual.")

PUNTAS_IDS = [4, 8, 12, 16, 20]  # Pulgar, Índice, Medio, Anular, Meñique
PIP_IDS = [2, 6, 10, 14, 18]     # Articulaciones intermedias
NOMBRES_DEDOS = ["Pulgar", "Indice", "Medio", "Anular", "Menique"]

def distancia_euclidiana(p1, p2):
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

def clasificar_dedos(puntos_px, mano_label, es_espejo=True):
    """Analiza los 21 landmarks de una mano para determinar qué dedos están extendidos."""
    estados = [0, 0, 0, 0, 0]

    # Dedos: Índice, Medio, Anular, Meñique (eje vertical Y)
    for i in range(1, 5):
        tip_y = puntos_px[PUNTAS_IDS[i]][1]
        pip_y = puntos_px[PIP_IDS[i]][1]
        if tip_y < pip_y:
            estados[i] = 1

    # Detección precisa del Pulgar
    p_tip_thumb = puntos_px[4]
    p_ip_thumb = puntos_px[3]
    p_mcp_thumb = puntos_px[2]
    p_wrist = puntos_px[0]
    p_index_mcp = puntos_px[5]
    p_index_pip = puntos_px[6]
    p_pinky_base = puntos_px[17]

    ref_escala = distancia_euclidiana(p_wrist, puntos_px[9])
    
    dist_tip_index_mcp = distancia_euclidiana(p_tip_thumb, p_index_mcp)
    dist_tip_index_pip = distancia_euclidiana(p_tip_thumb, p_index_pip)
    dist_tip_pinky = distancia_euclidiana(p_tip_thumb, p_pinky_base)
    dist_ip_pinky = distancia_euclidiana(p_ip_thumb, p_pinky_base)
    dist_tip_mcp = distancia_euclidiana(p_tip_thumb, p_mcp_thumb)
    dist_ip_mcp = distancia_euclidiana(p_ip_thumb, p_mcp_thumb)
    dist_tip_wrist = distancia_euclidiana(p_tip_thumb, p_wrist)
    dist_mcp_wrist = distancia_euclidiana(p_mcp_thumb, p_wrist)

    cerca_de_la_mano = (dist_tip_index_mcp < ref_escala * 0.44) or (dist_tip_index_pip < ref_escala * 0.35)
    doblado_hacia_palma = dist_tip_pinky < (dist_ip_pinky * 1.05)
    encogido = dist_tip_mcp < (dist_ip_mcp * 1.15)

    pulgar_abierto = False
    if not cerca_de_la_mano and not encogido:
        es_pulgar_arriba = (p_tip_thumb[1] < p_ip_thumb[1] < p_mcp_thumb[1]) and (dist_tip_wrist > dist_mcp_wrist * 1.2)
        mano_rel = mano_label if es_espejo else ("Left" if mano_label == "Right" else "Right")
        if mano_rel == "Right":
            es_lateral = (p_tip_thumb[0] < p_ip_thumb[0]) and (p_tip_thumb[0] < p_mcp_thumb[0])
        else:
            es_lateral = (p_tip_thumb[0] > p_ip_thumb[0]) and (p_tip_thumb[0] > p_mcp_thumb[0])

        if es_pulgar_arriba:
            pulgar_abierto = True
        elif es_lateral and not doblado_hacia_palma:
            pulgar_abierto = True

    estados[0] = 1 if pulgar_abierto else 0
    conteo = sum(estados)

    # Detección de Pellizco (Click)
    dist_pinch = distancia_euclidiana(puntos_px[4], puntos_px[8])
    ref_escala = distancia_euclidiana(puntos_px[0], puntos_px[9])
    pinch_activo = dist_pinch < max(24, int(ref_escala * 0.28))

    # Identificación de Gesto
    if pinch_activo:
        gesto = "Click / Pellizco"
    elif conteo == 0:
        gesto = "Puno cerrado"
    elif conteo == 5:
        gesto = "Mano abierta (5)"
    elif estados == [0, 1, 0, 0, 0]:
        gesto = "Senalando (1)"
    elif estados == [0, 1, 1, 0, 0]:
        gesto = "Paz / Victoria (2)"
    elif estados == [1, 1, 0, 0, 0]:
        gesto = "Pistola (L)"
    elif estados == [0, 1, 1, 1, 0]:
        gesto = "Tres dedos (3)"
    elif estados == [0, 1, 1, 1, 1]:
        gesto = "Cuatro dedos (4)"
    elif estados == [1, 0, 0, 0, 0]:
        if p_tip_thumb[1] < p_wrist[1]:
            gesto = "Pulgar Arriba (Like)"
        else:
            gesto = "Pulgar Abajo (Dislike)"
    elif estados in ([0, 1, 0, 0, 1], [1, 1, 0, 0, 1]):
        gesto = "Rock / Heavy Metal"
    elif estados == [1, 0, 0, 0, 1]:
        gesto = "Shaka / Surfer"
    elif estados == [0, 0, 1, 0, 0]:
        gesto = "Dedo Medio"
    else:
        gesto = f"{conteo} dedos"

    return estados, conteo, gesto, pinch_activo, dist_pinch

def obtener_indice_camara():
    """Detecta las cámaras disponibles en Linux/Jetson."""
    parser = argparse.ArgumentParser(description="Detector de Dedos y Gestos con MediaPipe")
    parser.add_argument("cam_posicional", nargs="?", type=int, default=None, help="Índice de cámara (0, 1...)")
    parser.add_argument("-c", "--camera", "--cam", type=int, default=None, dest="cam_flag", help="Índice de cámara web")
    args, _ = parser.parse_known_args()

    indice = args.cam_posicional if args.cam_posicional is not None else args.cam_flag
    if indice is not None:
        print(f"\n>> Cámara seleccionada por argumento: Cámara {indice}")
        return indice

    print("\n" + "=" * 55)
    print("      CONFIGURACIÓN Y SELECCIÓN DE CÁMARA")
    print("=" * 55)
    print(" Escaneando puertos de video disponibles...")

    camaras_activas = []
    for i in range(3):
        test_cap = cv2.VideoCapture(i)
        if test_cap.isOpened():
            ret, _ = test_cap.read()
            if ret:
                camaras_activas.append(i)
            test_cap.release()

    if not camaras_activas:
        camaras_activas = [0]

    print(" Cámaras detectadas:")
    for c in camaras_activas:
        tipo = f"Cámara en puerto /dev/video{c}"
        print(f"   [{c}] -> {tipo}")

    sugerida = camaras_activas[0]
    print("-" * 55)
    print(f"   [Enter] -> Usar automáticamente Cámara {sugerida}")
    print("=" * 55)

    try:
        entrada = input(f"Selecciona la cámara [Enter para Cámara {sugerida}]: ").strip()
        if entrada == "":
            return sugerida
        return int(entrada)
    except Exception:
        return sugerida

def main():
    indice_cam = obtener_indice_camara()
    print(f"\n[INICIANDO] Conectando a Cámara {indice_cam}...")

    cap = cv2.VideoCapture(indice_cam)

    if not cap.isOpened():
        print(f"[ERROR] No se pudo abrir la cámara {indice_cam}.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    mp_hands = mp.solutions.hands
    mp_drawing = mp.solutions.drawing_utils

    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.5
    )

    es_espejo = True
    prev_time = time.time()
    ultimo_envio_serial = 0
    fps = 30.0

    print("\n" + "=" * 55)
    print(f" DETECTOR DE DEDOS Y GESTOS INICIADO (CÁMARA {indice_cam})")
    print(" Presiona [C] para cambiar de cámara")
    print(" Presiona [M] para alternar espejo, [S] para guardar foto")
    print(" Presiona [Q] o [ESC] para salir")
    print("=" * 55 + "\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if es_espejo:
            frame = cv2.flip(frame, 1)

        h, w, _ = frame.shape

        t_actual = time.time()
        dt = t_actual - prev_time
        if dt > 0:
            fps = 0.9 * fps + 0.1 * (1.0 / dt)
        prev_time = t_actual

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb_frame.flags.writeable = False
        results = hands.process(rgb_frame)
        rgb_frame.flags.writeable = True

        total_dedos = 0
        gesto_actual = "Ninguno"
        indice_activo = False
        medio_activo = False

        # Encabezado
        cv2.rectangle(frame, (10, 10), (w - 10, 60), (20, 20, 30), -1)
        cv2.rectangle(frame, (10, 10), (w - 10, 60), (0, 255, 200), 1)
        cv2.putText(frame, "DETECTOR DE DEDOS - JETSON NANO", (25, 38),
                    cv2.FONT_HERSHEY_DUPLEX, 0.6, (0, 255, 200), 2)
        cv2.putText(frame, f"FPS: {int(fps)}", (w - 120, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        panel_y = 80
        if results.multi_hand_landmarks and results.multi_handedness:
            for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                etiqueta = handedness.classification[0].label
                puntos_px = [(int(lm.x * w), int(lm.y * h)) for lm in hand_landmarks.landmark]

                estados, conteo, gesto, pinch_activo, dist_pinch = clasificar_dedos(
                    puntos_px, etiqueta, es_espejo
                )
                total_dedos += conteo
                gesto_actual = gesto

                # Detección de dedos clave para activación de relés:
                # estados[1] = Dedo Índice -> Controla Relé 1
                # estados[2] = Dedo Medio  -> Controla Relé 2
                if estados[1] == 1:
                    indice_activo = True
                if estados[2] == 1:
                    medio_activo = True

                # Dibujar esqueleto de la mano
                mp_drawing.draw_landmarks(
                    frame,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS,
                    landmark_drawing_spec=mp_drawing.DrawingSpec(color=(0, 255, 255), thickness=2, circle_radius=3),
                    connection_drawing_spec=mp_drawing.DrawingSpec(color=(255, 140, 0), thickness=2)
                )

                # Resaltar puntas de los dedos
                for i, tip_id in enumerate(PUNTAS_IDS):
                    px, py = puntos_px[tip_id]
                    color_punto = (0, 255, 0) if estados[i] else (0, 0, 255)
                    cv2.circle(frame, (px, py), 8, color_punto, -1)
                    cv2.circle(frame, (px, py), 10, (255, 255, 255), 1)

                if pinch_activo:
                    mid = ((puntos_px[4][0] + puntos_px[8][0]) // 2, (puntos_px[4][1] + puntos_px[8][1]) // 2)
                    cv2.circle(frame, mid, 12, (0, 255, 255), -1)

                # Panel lateral
                cv2.rectangle(frame, (w - 240, panel_y), (w - 15, panel_y + 140), (25, 25, 35), -1)
                cv2.rectangle(frame, (w - 240, panel_y), (w - 15, panel_y + 140), (0, 255, 200), 1)
                cv2.putText(frame, f"{etiqueta.upper()}: {conteo} Dedos", (w - 225, panel_y + 25),
                            cv2.FONT_HERSHEY_DUPLEX, 0.5, (0, 255, 200), 1)
                cv2.putText(frame, f"{gesto}", (w - 225, panel_y + 45),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 100), 1)

                for i, nombre in enumerate(NOMBRES_DEDOS):
                    estado_str = "1" if estados[i] else "0"
                    col = (0, 255, 0) if estados[i] else (120, 120, 255)
                    cv2.putText(frame, f"{nombre}: {estado_str}", (w - 225, panel_y + 65 + i * 14),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, 1)

                panel_y += 150

        # Determinar comandos de activación de los relés según dedos levantados
        relay_1_cmd = "ON" if indice_activo else "OFF"
        relay_2_cmd = "ON" if medio_activo else "OFF"

        # Barra inferior con total de dedos
        cv2.rectangle(frame, (10, h - 50), (280, h - 10), (20, 20, 30), -1)
        cv2.rectangle(frame, (10, h - 50), (280, h - 10), (0, 255, 200), 1)
        cv2.putText(frame, f"DEDOS: {total_dedos}", (20, h - 22),
                    cv2.FONT_HERSHEY_DUPLEX, 0.65, (0, 255, 200), 2)

        # Panel indicador de Control de Relés en vivo
        rele_panel_x = 295
        rele_panel_w = 330
        cv2.rectangle(frame, (rele_panel_x, h - 50), (rele_panel_x + rele_panel_w, h - 10), (20, 20, 30), -1)
        cv2.rectangle(frame, (rele_panel_x, h - 50), (rele_panel_x + rele_panel_w, h - 10), (0, 255, 200), 1)

        col_r1 = (0, 255, 0) if indice_activo else (100, 100, 160)
        col_r2 = (0, 255, 0) if medio_activo else (100, 100, 160)
        cv2.putText(frame, f"RELE 1 (Indice): {relay_1_cmd}", (rele_panel_x + 10, h - 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, col_r1, 1)
        cv2.putText(frame, f"RELE 2 (Medio) : {relay_2_cmd}", (rele_panel_x + 10, h - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, col_r2, 1)

        # Enviar paquete JSON al ESP32 cada ~80ms por UART
        if esp32_serial and (t_actual - ultimo_envio_serial > 0.08):
            ultimo_envio_serial = t_actual
            comando_payload = {
                "status": "ok",
                "relay_command": relay_1_cmd,
                "relay_2_command": relay_2_cmd,
                "dedos": total_dedos,
                "gesto": gesto_actual
            }
            mensaje = json.dumps(comando_payload) + "\n"
            try:
                esp32_serial.write(mensaje.encode('utf-8'))
            except Exception:
                pass

        cv2.imshow("Detector de Dedos - Jetson Nano", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == ord('Q') or key == 27:
            break
        elif key == ord('m') or key == ord('M'):
            es_espejo = not es_espejo
        elif key == ord('c') or key == ord('C'):
            nuevo_indice = 1 if indice_cam == 0 else 0
            cap.release()
            nueva_cap = cv2.VideoCapture(nuevo_indice)
            if nueva_cap.isOpened():
                cap = nueva_cap
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                indice_cam = nuevo_indice
            else:
                cap = cv2.VideoCapture(indice_cam)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        elif key == ord('s') or key == ord('S'):
            nombre = f"captura_dedos_{int(time.time())}.jpg"
            cv2.imwrite(nombre, frame)
            print(f"[OK] Captura guardada como '{nombre}'")

    cap.release()
    cv2.destroyAllWindows()
    hands.close()
    if esp32_serial:
        esp32_serial.close()

if __name__ == "__main__":
    main()
