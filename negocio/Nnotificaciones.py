import os
import sqlite3
import json
import time
from datetime import datetime
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from pywebpush import webpush, WebPushException

# Cargar variables de entorno desde .env
load_dotenv()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CONFIG_ALERTAS_SENSORES_FILE = os.path.join(BASE_DIR, 'config_alertas_sensores.json')

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


def procesar_suscripcion(data, user_id=None):
    """
    Procesa y guarda los datos de la suscripción Web Push en la tabla 'suscripcion'
    asociada al usuario del dispositivo.
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

    # Extraer user_id del parámetro o del payload JSON
    if not user_id:
        user_id = data.get("id_usuario")

    print(f"Endpoint: {endpoint}")
    print(f"p256dh: {p256dh}")
    print(f"auth: {auth}")
    print(f"id_usuario: {user_id}")

    if not endpoint or not p256dh or not auth:
        return {"success": False, "message": "Faltan datos obligatorios de la suscripción"}, 400

    try:
        total = d_notificaciones.guardar_suscripcion(endpoint, p256dh, auth, id_usuario=user_id)

        print("✅ SUSCRIPCIÓN GUARDADA CORRECTAMENTE EN TABLA 'suscripcion'")
        print(f"Total de suscripciones activas: {total} (Usuario ID: {user_id})")

        return {
            "success": True,
            "message": "Suscripción guardada",
            "total": total,
            "id_usuario": user_id
        }, 200

    except Exception as e:
        print(f"❌ ERROR EN procesar_suscripcion: {repr(e)}")
        return {"success": False, "message": str(e)}, 500


def enviar_notificacion_push(title="🔔 Proyecto IoT", body="¡Esta es una notificación de prueba del sistema!", tipo="aviso", destinatarios="todos", user_ids=None, tag=None, url="/", renotify=True):
    """
    Envía una notificación Push a todas las suscripciones o a una lista específica de usuarios seleccionados.
    Soporta 'tag' para evitar acumulación de spam y 'url' para redirección al hacer clic.
    Cumple con la especificación W3C Web Notifications (renotify solo se incluye si tag existe).
    """
    if not title:
        title = "🔔 Proyecto IoT"
    if not body:
        body = "¡Esta es una notificación del sistema!"

    if destinatarios == "custom" and user_ids:
        subscriptions = d_notificaciones.obtener_suscripciones(user_ids=user_ids)
    else:
        subscriptions = d_notificaciones.obtener_suscripciones()

    # Siempre proveer un tag no vacío: si no se especifica tag (ej. difusión/broadcast),
    # generamos uno único con timestamp para evitar colisiones y asegurar 100% de compatibilidad
    # con la regla de Chrome: "renotify flag must specify a non-empty tag" tanto en SWs en caché como nuevos.
    tag_seguro = str(tag).strip() if (tag and str(tag).strip()) else f"iot-broadcast-{tipo}-{int(time.time() * 1000)}"

    payload_dict = {
        "title": title,
        "body": body,
        "tipo": tipo,
        "url": url or "/",
        "tag": tag_seguro,
        "renotify": bool(renotify)
    }

    payload = json.dumps(payload_dict)

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
            print(f"Error enviando WebPush a {subscription.get('usuario', 'desconocido')}: {e}")
            # Si el endpoint ya expiró o fue desregistrado (HTTP 404 / 410)
            if hasattr(e, 'response') and e.response and e.response.status_code in [404, 410]:
                try:
                    d_notificaciones.eliminar_suscripcion(subscription["endpoint"])
                    print(f"Suscripción expirada eliminada para usuario {subscription.get('usuario')}")
                except Exception:
                    pass
            elif "Invalid p256dh" in str(e) or "Invalid auth" in str(e):
                try:
                    d_notificaciones.eliminar_suscripcion(subscription["endpoint"])
                    print(f"Suscripción corrupta eliminada para usuario {subscription.get('usuario')}")
                except Exception:
                    pass

    return {
        "success": True,
        "enviados": enviados,
        "total_destinatarios": len(subscriptions)
    }


def obtener_usuarios_para_notificaciones():
    """
    Retorna la lista de usuarios y el conteo de dispositivos suscritos para la interfaz de envío selectivo.
    """
    return d_notificaciones.obtener_usuarios_para_notificaciones()


def obtener_suscripciones_debug():
    """
    Obtiene un resumen de suscripciones registradas en la tabla 'suscripcion'
    junto al usuario asociado para depuración a través de Dnotificaciones.
    """
    subscriptions = d_notificaciones.obtener_suscripciones()

    return [
        {
            "id": row["id"],
            "id_usuario": row.get("id_usuario"),
            "usuario": row.get("usuario"),
            "endpoint": row["endpoint"][:80] + "..." if len(row["endpoint"]) > 80 else row["endpoint"],
            "p256dh": row["p256dh"][:20] + "..." if len(row["p256dh"]) > 20 else row["p256dh"],
            "auth": row["auth"][:20] + "..." if len(row["auth"]) > 20 else row["auth"]
        }
        for row in subscriptions
    ]


# ==================== CONFIGURACIÓN DE ALERTAS DE SENSORES Y UMBRALES ====================

DEFAULT_CONFIG_ALERTAS_SENSORES = {
    "version": "1.1",
    "habilitado_global": True,
    "frecuencia_minutos": 20,
    "condicion_reporte": "solo_anomalias",  # "solo_anomalias" o "incluir_normal"
    "hardware_offline": {
        "esp32": True,
        "jetson": True
    },
    "destinatarios": "todos",  # "todos" o "custom"
    "usuarios_seleccionados": [1],
    "sensores": {
        "temperatura": {
            "habilitado": True,
            "nombre": "Temperatura Ambiental",
            "unidad": "°C",
            "min_normal": 14.0,
            "max_normal": 32.0
        },
        "humedad_suelo": {
            "habilitado": True,
            "nombre": "Humedad del Suelo",
            "unidad": "%",
            "min_normal": 25.0,
            "max_normal": 80.0
        },
        "calidad_aire": {
            "habilitado": True,
            "nombre": "Calidad de Aire / Gases",
            "unidad": "PPM",
            "min_normal": 0.0,
            "max_normal": 450.0
        },
        "presion": {
            "habilitado": False,
            "nombre": "Presión Barométrica",
            "unidad": "hPa",
            "min_normal": 980.0,
            "max_normal": 1030.0
        }
    }
}

# Buffer en memoria para control de anti-saturación de notificaciones push
_cache_alerta_sensores = {
    "ultimo_envio_ts": 0,
    "ultimo_estado": None  # "anomalia" o "normal"
}

_cache_hardware_offline = {
    "ultimo_envio_esp32_ts": 0,
    "ultimo_envio_jetson_ts": 0
}

def obtener_config_alertas_sensores():
    """
    Obtiene la configuración de umbrales, frecuencia, condición y destinatarios para alertas de sensores.
    """
    if not os.path.exists(CONFIG_ALERTAS_SENSORES_FILE):
        guardar_config_alertas_sensores(DEFAULT_CONFIG_ALERTAS_SENSORES)
        return dict(DEFAULT_CONFIG_ALERTAS_SENSORES)
    try:
        with open(CONFIG_ALERTAS_SENSORES_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            merged = json.loads(json.dumps(DEFAULT_CONFIG_ALERTAS_SENSORES))
            merged.update(cfg)
            if "sensores" in cfg:
                for k, v in cfg["sensores"].items():
                    if k in merged["sensores"]:
                        merged["sensores"][k].update(v)
            if "hardware_offline" in cfg:
                merged["hardware_offline"].update(cfg["hardware_offline"])
            return merged
    except Exception as e:
        print(f"Error leyendo configuración de alertas de sensores: {e}")
        return dict(DEFAULT_CONFIG_ALERTAS_SENSORES)

def guardar_config_alertas_sensores(nueva_config):
    """
    Valida y guarda la configuración de alertas bioclimáticas en el archivo JSON.
    """
    try:
        merged = json.loads(json.dumps(DEFAULT_CONFIG_ALERTAS_SENSORES))
        merged.update(nueva_config)
        if "sensores" in nueva_config:
            for k, v in nueva_config["sensores"].items():
                if k in merged["sensores"]:
                    merged["sensores"][k].update(v)
        if "hardware_offline" in nueva_config:
            merged["hardware_offline"].update(nueva_config["hardware_offline"])

        with open(CONFIG_ALERTAS_SENSORES_FILE, 'w', encoding='utf-8') as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        return True, "Configuración de alertas guardada exitosamente."
    except Exception as e:
        print(f"Error guardando configuración de alertas de sensores: {e}")
        return False, str(e)

def evaluar_y_despachar_alertas_sensores(lectura):
    """
    Evalúa en tiempo real la telemetría recibida del ESP32 contra los umbrales configurados.
    Aplica control anti-saturación por frecuencia (tag: alerta-sensores-iot) y condición de disparo.
    """
    global _cache_alerta_sensores
    cfg = obtener_config_alertas_sensores()

    # Si las alertas globales están silenciadas, no despachar
    if not cfg.get("habilitado_global", True):
        return

    sensores_cfg = cfg.get("sensores", {})
    temp = float(lectura.get('temperatura', 0))
    humedad_suelo = float(lectura.get('humedad_suelo', 0))
    # Para calidad de aire, soportar 'calidad_aire' o 'co2' o 'humo'
    aire = float(lectura.get('calidad_aire', lectura.get('co2', 400.0)))
    presion = float(lectura.get('presion', 0))

    anomalias = []

    # 1. Temperatura
    s_temp = sensores_cfg.get("temperatura", {})
    if s_temp.get("habilitado", True):
        t_min = float(s_temp.get("min_normal", 14.0))
        t_max = float(s_temp.get("max_normal", 32.0))
        if temp < t_min:
            anomalias.append(f"Temp: {temp:.1f}°C (< {t_min:.1f}°C Frío)")
        elif temp > t_max:
            anomalias.append(f"Temp: {temp:.1f}°C (> {t_max:.1f}°C Calor)")

    # 2. Humedad del Suelo
    s_suelo = sensores_cfg.get("humedad_suelo", {})
    if s_suelo.get("habilitado", True):
        h_min = float(s_suelo.get("min_normal", 25.0))
        h_max = float(s_suelo.get("max_normal", 80.0))
        if 0 < humedad_suelo < h_min:
            anomalias.append(f"Suelo: {humedad_suelo:.1f}% (< {h_min:.0f}% Sequía)")
        elif humedad_suelo > h_max:
            anomalias.append(f"Suelo: {humedad_suelo:.1f}% (> {h_max:.0f}% Saturación)")

    # 3. Calidad del Aire / Gases
    s_aire = sensores_cfg.get("calidad_aire", {})
    if s_aire.get("habilitado", True):
        a_max = float(s_aire.get("max_normal", 450.0))
        if aire >= a_max:
            anomalias.append(f"Aire: {aire:.0f} PPM (≥ {a_max:.0f} PPM Gases)")

    # 4. Presión Barométrica
    s_presion = sensores_cfg.get("presion", {})
    if s_presion.get("habilitado", False) and presion > 0:
        p_min = float(s_presion.get("min_normal", 980.0))
        p_max = float(s_presion.get("max_normal", 1030.0))
        if presion < p_min:
            anomalias.append(f"Presión: {presion:.1f} hPa (< {p_min:.0f} hPa Tormenta)")
        elif presion > p_max:
            anomalias.append(f"Presión: {presion:.1f} hPa (> {p_max:.0f} hPa Alta)")

    ahora = time.time()
    frecuencia_minutos = max(1, int(cfg.get("frecuencia_minutos", 20)))
    intervalo_segundos = frecuencia_minutos * 60
    tiempo_transcurrido = ahora - _cache_alerta_sensores["ultimo_envio_ts"]

    # Si todo está normal y la condición es 'solo_anomalias', omitir despacho
    condicion = cfg.get("condicion_reporte", "solo_anomalias")
    if len(anomalias) == 0 and condicion == "solo_anomalias":
        return

    # Verificar si ya transcurrió la ventana de anti-saturación
    if tiempo_transcurrido < intervalo_segundos and _cache_alerta_sensores["ultimo_envio_ts"] > 0:
        return

    destinatarios = cfg.get("destinatarios", "todos")
    user_ids = cfg.get("usuarios_seleccionados", None) if destinatarios == "custom" else None

    try:
        if len(anomalias) > 0:
            titulo = f"⚠️ Alerta Bioclimática: {len(anomalias)} variable(s) fuera de rango"
            cuerpo = f"{' • '.join(anomalias)}. Despacho cada {frecuencia_minutos} min. Clic para ver panel."
            tipo = "danger"
        else:
            titulo = "🌿 Invernadero Fragaria: Todos los Sensores en Rango Normal"
            cuerpo = f"Temp: {temp:.1f}°C, Suelo: {humedad_suelo:.1f}%, Aire: {aire:.0f} PPM. Parámetros en equilibrio óptimo."
            tipo = "aviso"

        enviar_notificacion_push(
            title=titulo,
            body=cuerpo,
            tipo=tipo,
            destinatarios=destinatarios,
            user_ids=user_ids,
            tag="alerta-sensores-iot",
            url="/",
            renotify=True
        )

        _cache_alerta_sensores["ultimo_envio_ts"] = ahora
        _cache_alerta_sensores["ultimo_estado"] = "anomalia" if len(anomalias) > 0 else "normal"
    except Exception as e:
        print(f"Error despachando alerta push de sensores: {e}")

def verificar_y_despachar_hardware_offline(relay_state=None, jetson_online=None):
    """
    Verifica si el ESP32 o la Jetson Nano quedaron fuera de servicio y despacha alertas push si corresponde.
    """
    global _cache_hardware_offline
    cfg = obtener_config_alertas_sensores()
    if not cfg.get("habilitado_global", True):
        return

    hw = cfg.get("hardware_offline", {})
    ahora = time.time()
    destinatarios = cfg.get("destinatarios", "todos")
    user_ids = cfg.get("usuarios_seleccionados", None) if destinatarios == "custom" else None

    # ESP32 Offline (> 180 segundos sin telemetría)
    if hw.get("esp32", True) and relay_state and "last_esp32_seen" in relay_state:
        ultimo_esp32 = relay_state.get("last_esp32_seen", 0)
        if ultimo_esp32 > 0 and (ahora - ultimo_esp32) > 180:
            if (ahora - _cache_hardware_offline["ultimo_envio_esp32_ts"]) > 1200: # cada 20 min
                try:
                    enviar_notificacion_push(
                        title="🚨 Dispositivo Desconectado: ESP32 Fuera de Servicio",
                        body="El microcontrolador ESP32 lleva más de 3 minutos sin emitir datos recientes de telemetría. La conexión WiFi o alimentación eléctrica podrían estar interrumpidas.",
                        tipo="danger",
                        destinatarios=destinatarios,
                        user_ids=user_ids,
                        tag="hardware-esp32-offline",
                        url="/",
                        renotify=True
                    )
                    _cache_hardware_offline["ultimo_envio_esp32_ts"] = ahora
                except Exception as e:
                    print(f"Error despachando alerta ESP32 offline: {e}")

    # Jetson Nano Offline
    if hw.get("jetson", True) and jetson_online is False:
        if (ahora - _cache_hardware_offline["ultimo_envio_jetson_ts"]) > 1200:
            try:
                enviar_notificacion_push(
                    title="🚨 Módulo IA Desconectado: NVIDIA Jetson Fuera de Servicio",
                    body="La NVIDIA Jetson Nano o el contenedor de inferencia YOLO han dejado de responder al servidor. La detección de frutos por cámara está en pausa.",
                    tipo="danger",
                    destinatarios=destinatarios,
                    user_ids=user_ids,
                    tag="hardware-jetson-offline",
                    url="/detecciones",
                    renotify=True
                )
                _cache_hardware_offline["ultimo_envio_jetson_ts"] = ahora
            except Exception as e:
                print(f"Error despachando alerta Jetson offline: {e}")

def simular_prueba_push(escenario='anomalia', destinatarios=None, user_ids=None):
    """
    Envía una notificación push simulada de prueba para validar en vivo el funcionamiento de los Web Push.
    """
    cfg = obtener_config_alertas_sensores()
    if destinatarios is None:
        destinatarios = cfg.get("destinatarios", "todos")
    if user_ids is None and destinatarios == "custom":
        user_ids = cfg.get("usuarios_seleccionados", None)

    frec = cfg.get("frecuencia_minutos", 20)

    if escenario == 'esp32_offline':
        title = "🚨 Dispositivo Desconectado: ESP32 Fuera de Servicio"
        body = "El microcontrolador ESP32 lleva más de 3 minutos sin emitir datos recientes de telemetría. La conexión WiFi o alimentación eléctrica podrían estar interrumpidas."
        tag = "hardware-esp32-offline"
        tipo = "danger"
        url = "/"
    elif escenario == 'jetson_offline':
        title = "🚨 Módulo IA Desconectado: NVIDIA Jetson Fuera de Servicio"
        body = "La NVIDIA Jetson Nano o el contenedor de inferencia YOLO han dejado de responder al servidor. La detección de frutos por cámara está en pausa."
        tag = "hardware-jetson-offline"
        tipo = "danger"
        url = "/detecciones"
    elif escenario == 'normal':
        title = "🌿 Invernadero Fragaria: Todos los Sensores en Rango Normal"
        body = f"Temp: 23.5°C, Suelo: 58%, Aire: 380 PPM. Todos los parámetros se encuentran en balance óptimo. Despacho cada {frec} min."
        tag = "alerta-sensores-iot"
        tipo = "aviso"
        url = "/"
    else: # anomalia
        title = "⚠️ Alerta Bioclimática: 2 variable(s) fuera de rango normal"
        body = f"Temperatura: 34.5°C (Supera límite 32.0°C) • Suelo: 18% (Inferior a 25%). Despacho cada {frec} min con tag anti-spam. Clic para ver panel."
        tag = "alerta-sensores-iot"
        tipo = "danger"
        url = "/"

    return enviar_notificacion_push(
        title=title,
        body=body,
        tipo=tipo,
        destinatarios=destinatarios,
        user_ids=user_ids,
        tag=tag,
        url=url,
        renotify=True
    )

def verificar_alertas_sensores(lectura, umbrales=None):
    """
    Evalúa si la lectura actual genera alertas visuales para el panel de telemetría.
    Usa la configuración dinámica de umbrales para evaluar mín/máx de temperatura, humedad de suelo, aire y presión.
    """
    alertas = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Si se pasan umbrales legados explícitos
    if umbrales and isinstance(umbrales, dict) and "temperatura_max" in umbrales:
        temp = float(lectura.get('temperatura', 0))
        if temp >= umbrales.get("temperatura_max", 40.0):
            alertas.append({
                "tipo": "temperatura",
                "nivel": "danger",
                "mensaje": f"¡Alerta! Temperatura crítica: {temp:.1f}°C",
                "timestamp": timestamp
            })
        co2 = float(lectura.get('co2', 400.0))
        if co2 >= umbrales.get("co2_max", 1000.0):
            alertas.append({
                "tipo": "co2",
                "nivel": "warning",
                "mensaje": f"¡Advertencia! CO2 elevado: {co2:.1f} ppm",
                "timestamp": timestamp
            })
        humo = float(lectura.get('humo', 0.0))
        if humo >= umbrales.get("humo_max", 50.0):
            alertas.append({
                "tipo": "humo",
                "nivel": "danger",
                "mensaje": f"¡Alerta! Humo detectado: {humo:.1f}%",
                "timestamp": timestamp
            })
        humedad_suelo = float(lectura.get('humedad_suelo', 0.0))
        if 0 < humedad_suelo < umbrales.get("humedad_suelo_min", 20.0):
            alertas.append({
                "tipo": "humedad_suelo",
                "nivel": "warning",
                "mensaje": f"¡Advertencia! Humedad de suelo baja: {humedad_suelo:.1f}%",
                "timestamp": timestamp
            })
        return alertas

    # Evaluación dinámica con la configuración activa
    cfg = obtener_config_alertas_sensores()
    s_cfg = cfg.get("sensores", {})

    temp = float(lectura.get('temperatura', 0))
    humedad_suelo = float(lectura.get('humedad_suelo', 0))
    aire = float(lectura.get('calidad_aire', lectura.get('co2', 400.0)))
    presion = float(lectura.get('presion', 0))

    if s_cfg.get("temperatura", {}).get("habilitado", True):
        t_min = float(s_cfg["temperatura"].get("min_normal", 14.0))
        t_max = float(s_cfg["temperatura"].get("max_normal", 32.0))
        if temp < t_min:
            alertas.append({
                "tipo": "temperatura",
                "nivel": "info",
                "mensaje": f"¡Aviso! Temperatura baja: {temp:.1f}°C (< {t_min:.1f}°C)",
                "timestamp": timestamp
            })
        elif temp > t_max:
            alertas.append({
                "tipo": "temperatura",
                "nivel": "danger",
                "mensaje": f"¡Alerta! Temperatura excesiva: {temp:.1f}°C (> {t_max:.1f}°C)",
                "timestamp": timestamp
            })

    if s_cfg.get("humedad_suelo", {}).get("habilitado", True):
        h_min = float(s_cfg["humedad_suelo"].get("min_normal", 25.0))
        h_max = float(s_cfg["humedad_suelo"].get("max_normal", 80.0))
        if 0 < humedad_suelo < h_min:
            alertas.append({
                "tipo": "humedad_suelo",
                "nivel": "warning",
                "mensaje": f"¡Advertencia! Suelo seco: {humedad_suelo:.1f}% (< {h_min:.0f}%)",
                "timestamp": timestamp
            })
        elif humedad_suelo > h_max:
            alertas.append({
                "tipo": "humedad_suelo",
                "nivel": "info",
                "mensaje": f"¡Aviso! Suelo saturado: {humedad_suelo:.1f}% (> {h_max:.0f}%)",
                "timestamp": timestamp
            })

    if s_cfg.get("calidad_aire", {}).get("habilitado", True):
        a_max = float(s_cfg["calidad_aire"].get("max_normal", 450.0))
        if aire >= a_max:
            alertas.append({
                "tipo": "co2",
                "nivel": "danger",
                "mensaje": f"¡Alerta! Gases/CO2 elevados: {aire:.0f} PPM (≥ {a_max:.0f} PPM)",
                "timestamp": timestamp
            })

    if s_cfg.get("presion", {}).get("habilitado", False) and presion > 0:
        p_min = float(s_cfg["presion"].get("min_normal", 980.0))
        p_max = float(s_cfg["presion"].get("max_normal", 1030.0))
        if presion < p_min:
            alertas.append({
                "tipo": "presion",
                "nivel": "warning",
                "mensaje": f"¡Aviso! Presión barométrica baja: {presion:.1f} hPa (< {p_min:.0f} hPa)",
                "timestamp": timestamp
            })
        elif presion > p_max:
            alertas.append({
                "tipo": "presion",
                "nivel": "info",
                "mensaje": f"¡Aviso! Presión barométrica alta: {presion:.1f} hPa (> {p_max:.0f} hPa)",
                "timestamp": timestamp
            })

    return alertas
