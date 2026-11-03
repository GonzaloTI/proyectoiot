import os
import sqlite3
import json
from datetime import datetime
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from pywebpush import webpush, WebPushException

# Cargar variables de entorno desde .env
load_dotenv()

DATABASE = "datos.db"

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "private_key.pem")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_EMAIL = os.getenv("VAPID_EMAIL", "admin@example.com")

VAPID_CLAIMS = {
    "sub": f"mailto:{VAPID_EMAIL}"
}


from modelos.Dnotificaciones import Dnotificaciones

# Instancia del modelo Dnotificaciones para la capa de negocio
d_notificaciones = Dnotificaciones()

def init_push_db():
    """Inicializa la tabla de suscripciones Web Push a través del modelo Dnotificaciones."""
    d_notificaciones.inicializar_tabla()


def procesar_suscripcion(data):
    """
    Procesa y guarda los datos de la suscripción Web Push enviada desde el navegador.
    """
    print("\n==============================")
    print("📩 RECIBIENDO SUSCRIPCIÓN WEB PUSH")
    print("==============================")

    if not data:
        return {"success": False, "message": "No llegó JSON payload"}, 400

    endpoint = data.get("endpoint")
    keys = data.get("keys", {})

    # Permitir p256dh y auth desde el diccionario 'keys' o directo del objeto
    p256dh = keys.get("p256dh") if isinstance(keys, dict) else None
    auth = keys.get("auth") if isinstance(keys, dict) else None

    if not p256dh:
        p256dh = data.get("p256dh")
    if not auth:
        auth = data.get("auth")

    print(f"Endpoint: {endpoint}")
    print(f"p256dh: {p256dh}")
    print(f"auth: {auth}")

    if not endpoint or not p256dh or not auth:
        return {"success": False, "message": "Faltan datos obligatorios de la suscripción"}, 400

    try:
        total = d_notificaciones.guardar_suscripcion(endpoint, p256dh, auth)

        print("✅ SUSCRIPCIÓN GUARDADA CORRECTAMENTE")
        print(f"Total de suscripciones activas: {total}")

        return {
            "success": True,
            "message": "Suscripción guardada",
            "total": total
        }, 200

    except Exception as e:
        print(f"❌ ERROR EN procesar_suscripcion: {repr(e)}")
        return {"success": False, "message": str(e)}, 500


def enviar_notificacion_push(title="🔔 Proyecto IoT", body="¡Esta es una notificación de prueba del sistema!", tipo="aviso"):
    """
    Envía una notificación Push a todas las suscripciones registradas a través de Dnotificaciones.
    """
    subscriptions = d_notificaciones.obtener_suscripciones()

    payload = json.dumps({
        "title": title,
        "body": body,
        "tipo": tipo
    })

    enviados = 0

    for subscription in subscriptions:
        subscription_info = {
            "endpoint": subscription["endpoint"],
            "keys": {
                "p256dh": subscription["p256dh"],
                "auth": subscription["auth"]
            }
        }

        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS
            )
            enviados += 1
        except WebPushException as e:
            print(f"Error enviando WebPush: {e}")

    return {
        "success": True,
        "enviados": enviados
    }


def obtener_suscripciones_debug():
    """
    Obtiene un resumen de suscripciones registradas para depuración a través de Dnotificaciones.
    """
    subscriptions = d_notificaciones.obtener_suscripciones()

    return [
        {
            "id": row["id"],
            "endpoint": row["endpoint"][:80] + "..." if len(row["endpoint"]) > 80 else row["endpoint"],
            "p256dh": row["p256dh"][:20] + "..." if len(row["p256dh"]) > 20 else row["p256dh"],
            "auth": row["auth"][:20] + "..." if len(row["auth"]) > 20 else row["auth"]
        }
        for row in subscriptions
    ]


# Evaluación de alertas de sensores para soporte del módulo
UMBRALES_ALERTAS = {
    "temperatura_max": 40.0,
    "co2_max": 1000.0,
    "humo_max": 50.0,
    "humedad_suelo_min": 20.0
}

def verificar_alertas_sensores(lectura, umbrales=None):
    if umbrales is None:
        umbrales = UMBRALES_ALERTAS

    alertas = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    temp = float(lectura.get('temperatura', 0))
    if temp >= umbrales["temperatura_max"]:
        alertas.append({
            "tipo": "temperatura",
            "nivel": "danger",
            "mensaje": f"¡Alerta! Temperatura crítica: {temp:.1f}°C",
            "timestamp": timestamp
        })

    co2 = float(lectura.get('co2', 400.0))
    if co2 >= umbrales["co2_max"]:
        alertas.append({
            "tipo": "co2",
            "nivel": "warning",
            "mensaje": f"¡Advertencia! CO2 elevado: {co2:.1f} ppm",
            "timestamp": timestamp
        })

    humo = float(lectura.get('humo', 0.0))
    if humo >= umbrales["humo_max"]:
        alertas.append({
            "tipo": "humo",
            "nivel": "danger",
            "mensaje": f"¡Alerta! Humo detectado: {humo:.1f}%",
            "timestamp": timestamp
        })

    humedad_suelo = float(lectura.get('humedad_suelo', 0.0))
    if 0 < humedad_suelo < umbrales["humedad_suelo_min"]:
        alertas.append({
            "tipo": "humedad_suelo",
            "nivel": "warning",
            "mensaje": f"¡Advertencia! Humedad de suelo baja: {humedad_suelo:.1f}%",
            "timestamp": timestamp
        })

    return alertas
