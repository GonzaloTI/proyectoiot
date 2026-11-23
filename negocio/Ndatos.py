import time
from datetime import datetime
from negocio.Nnotificaciones import verificar_alertas_sensores, evaluar_y_despachar_alertas_sensores
from modelos.Ddatos import Ddatos
from negocio.Nactuadores import evaluar_automatizacion_inteligente

# Instancia del modelo de datos Ddatos para la capa de negocio
d_datos = Ddatos()

def procesar_y_guardar_datos(data, relay_state):
    """
    Procesa la lectura entrante del ESP32, actualiza el estado del relé,
    persiste los datos en la base de datos a través del modelo Ddatos,
    evalúa alertas de sensores y determina la respuesta con el comando.
    """
    temperatura = float(data.get('temperatura', 0))
    presion = float(data.get('presion', 0))
    altitud = float(data.get('altitud', 0))
    relay_activo = bool(data.get('relay_activo', False))
    relay_2_activo = bool(data.get('relay_2_activo', False))
    co2 = float(data.get('co2', 400.0))
    humo = float(data.get('humo', 0.0))
    humedad_suelo = float(data.get('humedad_suelo', 0.0))

    # Actualizar estado de los relés reportado por el dispositivo y timestamp de presencia
    relay_state["last_esp32_relay_status"] = relay_activo
    relay_state["last_esp32_relay_2_status"] = relay_2_activo
    relay_state["last_esp32_seen"] = time.time()

    # Guardar la lectura a través del modelo de datos Ddatos (sin modificar esquema de BD)
    try:
        d_datos.guardar_lectura(temperatura, presion, altitud, relay_activo, co2, humo, humedad_suelo)
    except Exception as e:
        print(f"Error guardando datos en la BD: {e}")

    # Evaluar y despachar alertas Web Push si corresponde (anti-saturación por frecuencia)
    try:
        evaluar_y_despachar_alertas_sensores(data)
    except Exception as e:
        print(f"Error en evaluación de alertas push: {e}")

    # Evaluar alertas visuales en función de los umbrales dinámicos
    alertas = verificar_alertas_sensores({
        'temperatura': temperatura,
        'co2': co2,
        'humo': humo,
        'humedad_suelo': humedad_suelo,
        'presion': presion
    })

    # Determinar el modo y comandos para enviar al ESP32
    if relay_state.get("manual_mode", False):
        mode_str = "manual"
        comando_1 = "ON" if relay_state.get("manual_state", False) else "OFF"
        comando_2 = "ON" if relay_state.get("manual_state_2", False) else "OFF"
        evaluacion_smart = None
    else:
        # Modo Automatización Inteligente gobernado por reglas (Horarios + Sensores)
        mode_str = "smart"
        evaluacion_smart = evaluar_automatizacion_inteligente(data)
        comando_1 = evaluacion_smart["rele1"]["command"]
        comando_2 = evaluacion_smart["rele2"]["command"]
        relay_state["smart_eval"] = evaluacion_smart

    return {
        "status": "ok",
        "mode": mode_str,
        "relay_command": comando_1,
        "relay_2_command": comando_2,
        "smart_eval": evaluacion_smart,
        "alertas": alertas
    }


def obtener_historial(relay_state, limit=50):
    """
    Obtiene las últimas lecturas registradas formateadas para los gráficos del dashboard a través de Ddatos.
    """
    try:
        rows = d_datos.obtener_historial(limit=limit)
        history_list = []
        for r in rows:
            history_list.append({
                "timestamp": r[0].split(" ")[1] if " " in r[0] else r[0],  # Formato hora (HH:MM:SS)
                "temperatura": r[1],
                "presion": r[2],
                "altitud": r[3],
                "relay_activo": bool(r[4]),
                "co2": r[5] if len(r) > 5 else 400.0,
                "humo": r[6] if len(r) > 6 else 0.0,
                "humedad_suelo": r[7] if len(r) > 7 else 0.0
            })
    except Exception as e:
        print(f"Error obteniendo historial: {e}")
        history_list = []

    return {
        "history": history_list,
        "relay_state": relay_state
    }


def actualizar_estado_rele(relay_state, data):
    """
    Actualiza la configuración manual o automática de los relés enviada por la interfaz.
    Si se solicita alternar o forzar un relé, activa el modo manual para darle prioridad al operador.
    Si se desactiva manual_mode (o se activa automatización), reanuda el control inteligente y re-evalúa.
    """
    if "manual_mode" in data:
        relay_state["manual_mode"] = bool(data["manual_mode"])

    # Soporte para toggle simple {"relay": 1} o {"relay_id": 1}
    relay_num = data.get("relay") or data.get("relay_id")
    if relay_num is not None:
        rid = int(relay_num)
        if data.get("manual_mode") is False:
            relay_state["manual_mode"] = False
        elif "state" in data or "manual_state" in data or "manual_state_2" in data:
            relay_state["manual_mode"] = True
            if "state" in data:
                target_state = bool(data["state"])
            else:
                # Si no viene estado explícito, alternar el estado actual
                curr = relay_state.get("manual_state", False) if rid == 1 else relay_state.get("manual_state_2", False)
                target_state = not curr

            if rid == 1:
                relay_state["manual_state"] = target_state
            elif rid == 2:
                relay_state["manual_state_2"] = target_state

    if "manual_state" in data and data.get("manual_mode") is not False:
        relay_state["manual_mode"] = True
        relay_state["manual_state"] = bool(data["manual_state"])

    if "manual_state_2" in data and data.get("manual_mode") is not False:
        relay_state["manual_mode"] = True
        relay_state["manual_state_2"] = bool(data["manual_state_2"])

    # Si se desactiva el modo manual (reanudando automatización), re-evaluar de inmediato con datos recientes
    if not relay_state.get("manual_mode", False):
        try:
            from modelos.Ddatos import Ddatos
            from negocio.Nactuadores import evaluar_automatizacion_inteligente
            d = Ddatos()
            history = d.obtener_historial(limit=1)
            if history and len(history) > 0:
                row = history[0]
                telemetria = {
                    "temperatura": row[1] if len(row) > 1 else 20.0,
                    "presion": row[2] if len(row) > 2 else 1013.0,
                    "altitud": row[3] if len(row) > 3 else 0.0,
                    "co2": row[5] if len(row) > 5 else 400.0,
                    "humo": row[6] if len(row) > 6 else 0.0,
                    "humedad_suelo": row[7] if len(row) > 7 else 50.0
                }
                evaluacion = evaluar_automatizacion_inteligente(telemetria)
                relay_state["smart_eval"] = evaluacion
        except Exception as e:
            print(f"Error evaluando smart tras toggle manual_mode: {e}")

    return {
        "status": "ok",
        "relay_state": relay_state
    }


def obtener_fechas_historial():
    """
    Obtiene la lista de fechas únicas disponibles en la base de datos a través de Ddatos.
    """
    try:
        return d_datos.obtener_fechas_disponibles()
    except Exception as e:
        print(f"Error obteniendo fechas de historial: {e}")
        return []


def obtener_historial_diario(date_str=None):
    """
    Obtiene los datos detallados y estadísticas consolidadas para una fecha específica a través de Ddatos.
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    try:
        history = d_datos.obtener_datos_diarios(date_str)
        stats = d_datos.obtener_estadisticas_diarias(date_str)
    except Exception as e:
        print(f"Error obteniendo datos diarios: {e}")
        history = []
        stats = {}

    return {
        "date": date_str,
        "history": history,
        "stats": stats
    }
