import os
import json
from datetime import datetime

CONFIG_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config_actuadores.json')

DEFAULT_CONFIG = {
    "version": "1.0",
    "rele1": {
        "alias": "Bomba de Riego",
        "pin": 4,
        "enabled": True,
        "mode": "hibrido",  # "horario", "sensor", "hibrido"
        "schedule": {
            "startTime": "06:30",
            "endTime": "08:00",
            "days": [0, 1, 2, 3, 4, 5, 6],  # 0: Dom, 1: Lun, ... 6: Sáb
            "maxRuntimeMinutes": 15
        },
        "sensorRules": {
            "useSoil": True,
            "soilMinTrigger": 35.0,  # Encender si humedad < 35%
            "soilMaxCut": 75.0,      # Apagar si humedad >= 75%
            "useTemp": True,
            "tempMinAllowed": 14.0,  # Temp mínima para regar
            "tempMaxAllowed": 30.0   # Temp máxima para regar
        }
    },
    "rele2": {
        "alias": "Extractor de Ventilación",
        "pin": 5,
        "enabled": True,
        "mode": "hibrido",  # "horario", "sensor", "hibrido"
        "schedule": {
            "startTime": "11:00",
            "endTime": "18:00",
            "days": [0, 1, 2, 3, 4, 5, 6]
        },
        "sensorRules": {
            "useTemp": True,
            "tempTrigger": 27.0,     # Disparo por calor >= 27.0°C
            "tempCut": 25.0,         # Histéresis de corte <= 25.0°C
            "useAir": True,
            "airPpmTrigger": 400.0   # Disparo por gases/humo >= 400 PPM
        }
    }
}

# Cache en memoria
_cached_config = None


def obtener_config_actuadores():
    """
    Carga la configuración de automatización de actuadores desde el archivo JSON persistente.
    Si no existe, crea el archivo con los valores predeterminados.
    """
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                _cached_config = json.load(f)
                return _cached_config
        except Exception as e:
            print(f"⚠️ Error leyendo {CONFIG_FILE_PATH}: {e}. Usando defaults.")

    _cached_config = dict(DEFAULT_CONFIG)
    guardar_config_actuadores(_cached_config)
    return _cached_config


def guardar_config_actuadores(nueva_config):
    """
    Guarda y persiste la configuración de actuadores en disco.
    """
    global _cached_config
    try:
        # Asegurar estructura mínima
        merged = dict(DEFAULT_CONFIG)
        if "rele1" in nueva_config:
            merged["rele1"].update(nueva_config["rele1"])
        if "rele2" in nueva_config:
            merged["rele2"].update(nueva_config["rele2"])
        merged["ultima_modificacion"] = datetime.now().isoformat()

        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)

        _cached_config = merged
        return True, "Configuración guardada exitosamente."
    except Exception as e:
        print(f"❌ Error guardando config actuadores: {e}")
        return False, str(e)


def _time_str_to_minutes(time_str):
    try:
        parts = time_str.split(':')
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 0


def evaluar_automatizacion_inteligente(telemetria, config=None, dt_actual=None):
    """
    Evalúa las reglas de Automatización Inteligente en función de la telemetría
    en tiempo real y la hora actual del servidor.

    Retorna un diccionario con los comandos resultantes ("ON" / "OFF") para cada relé
    y los motivos/diagnósticos de la decisión.
    """
    if config is None:
        config = obtener_config_actuadores()

    if dt_actual is None:
        dt_actual = datetime.now()

    # Minutos transcurridos desde medianoche (0 - 1439)
    now_min = dt_actual.hour * 60 + dt_actual.minute
    # Día de la semana en formato JS: 0=Domingo, 1=Lunes, ... 6=Sábado
    now_day_js = (dt_actual.weekday() + 1) % 7

    temp = float(telemetria.get('temperatura', 0.0))
    humedad_suelo = float(telemetria.get('humedad_suelo', 0.0))
    co2 = float(telemetria.get('co2', 400.0))
    humo = float(telemetria.get('humo', 0.0))

    # ----------------------------------------------------
    # 1. EVALUAR RELÉ 1 (Bomba de Riego / Agua - GPIO 4)
    # ----------------------------------------------------
    r1 = config.get("rele1", {})
    r1_enabled = r1.get("enabled", True)
    r1_active = False
    r1_reason = ""

    if not r1_enabled:
        r1_active = False
        r1_reason = "Automatización deshabilitada para Relé 1."
    else:
        sched = r1.get("schedule", {})
        start_min = _time_str_to_minutes(sched.get("startTime", "06:30"))
        end_min = _time_str_to_minutes(sched.get("endTime", "08:00"))
        days = sched.get("days", [0, 1, 2, 3, 4, 5, 6])

        # Verificación horaria
        if start_min <= end_min:
            in_schedule = (start_min <= now_min <= end_min)
        else:
            in_schedule = (now_min >= start_min or now_min <= end_min)
        day_matches = (now_day_js in days)
        schedule_valid = (in_schedule and day_matches)

        # Verificación de sensores
        s_rules = r1.get("sensorRules", {})
        use_soil = s_rules.get("useSoil", True)
        soil_min = float(s_rules.get("soilMinTrigger", 35.0))
        soil_needs_water = (humedad_suelo < soil_min) if use_soil else True

        use_temp = s_rules.get("useTemp", True)
        t_min = float(s_rules.get("tempMinAllowed", 14.0))
        t_max = float(s_rules.get("tempMaxAllowed", 30.0))
        temp_allowed = (t_min <= temp <= t_max) if use_temp else True

        mode = r1.get("mode", "hibrido")

        if mode == "horario":
            r1_active = schedule_valid
            r1_reason = "Horario programado activo" if schedule_valid else "Fuera de horario programado"
        elif mode == "sensor":
            r1_active = (soil_needs_water and temp_allowed)
            r1_reason = f"Disparo sensor: Suelo {humedad_suelo}% < {soil_min}%" if r1_active else "Suelo con humedad suficiente o temp fuera de rango"
        else:  # "hibrido" (horario + sensores)
            if schedule_valid and soil_needs_water and temp_allowed:
                r1_active = True
                r1_reason = f"Ventana horaria activa y suelo seco ({humedad_suelo}% < {soil_min}%)"
            elif not schedule_valid:
                r1_active = False
                r1_reason = "Fuera de ventana horaria de riego"
            elif not soil_needs_water:
                r1_active = False
                r1_reason = f"En horario pero suelo húmedo ({humedad_suelo}% >= {soil_min}%)"
            else:
                r1_active = False
                r1_reason = f"Temperatura ({temp}°C) fuera de rango seguro ({t_min}°C - {t_max}°C)"

    # ----------------------------------------------------
    # 2. EVALUAR RELÉ 2 (Extractor de Ventilación - GPIO 5)
    # ----------------------------------------------------
    r2 = config.get("rele2", {})
    r2_enabled = r2.get("enabled", True)
    r2_active = False
    r2_reason = ""

    if not r2_enabled:
        r2_active = False
        r2_reason = "Automatización deshabilitada para Relé 2."
    else:
        sched2 = r2.get("schedule", {})
        start_min2 = _time_str_to_minutes(sched2.get("startTime", "11:00"))
        end_min2 = _time_str_to_minutes(sched2.get("endTime", "18:00"))
        days2 = sched2.get("days", [0, 1, 2, 3, 4, 5, 6])

        if start_min2 <= end_min2:
            in_schedule2 = (start_min2 <= now_min <= end_min2)
        else:
            in_schedule2 = (now_min >= start_min2 or now_min <= end_min2)
        day_matches2 = (now_day_js in days2)
        schedule_valid2 = (in_schedule2 and day_matches2)

        s_rules2 = r2.get("sensorRules", {})
        use_temp2 = s_rules2.get("useTemp", True)
        temp_trig = float(s_rules2.get("tempTrigger", 27.0))
        is_thermal_emergency = use_temp2 and (temp >= temp_trig)

        use_air = s_rules2.get("useAir", True)
        air_trig = float(s_rules2.get("airPpmTrigger", 400.0))
        is_air_contaminated = use_air and (co2 >= air_trig or humo >= air_trig)

        mode2 = r2.get("mode", "hibrido")

        # Emergencias térmicas o de aire siempre tienen máxima prioridad
        if is_thermal_emergency:
            r2_active = True
            r2_reason = f"🔥 Alerta Térmica: Temp ({temp:.1f}°C) >= {temp_trig}°C (Extractor ON)"
        elif is_air_contaminated:
            r2_active = True
            r2_reason = f"🌫️ Purga de Aire: Gases ({max(co2, humo):.0f} PPM) >= {air_trig} PPM"
        elif mode2 == "horario":
            r2_active = schedule_valid2
            r2_reason = "Ventilación diurna por horario" if schedule_valid2 else "Fuera de horario de ventilación"
        elif mode2 == "sensor":
            r2_active = False
            r2_reason = "Temperatura y gases en niveles seguros"
        else:  # "hibrido"
            if schedule_valid2:
                r2_active = True
                r2_reason = "Ventilación de rutina activa en ventana horaria"
            else:
                r2_active = False
                r2_reason = "Clima templado y fuera de horario de extracción"

    return {
        "rele1": {
            "command": "ON" if r1_active else "OFF",
            "active": r1_active,
            "reason": r1_reason
        },
        "rele2": {
            "command": "ON" if r2_active else "OFF",
            "active": r2_active,
            "reason": r2_reason
        }
    }

