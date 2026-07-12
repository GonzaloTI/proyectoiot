from flask import Flask, request, jsonify, render_template
from datos import Database

app = Flask(__name__)

# Instancia de la Base de Datos (creará 'datos.db' por defecto)
db = Database()

# Configuración del estado global del relé
relay_state = {
    "manual_mode": False,       # False = Automático (por temperatura >= 40°C), True = Manual
    "manual_state": False,      # True = Encendido (ON), False = Apagado (OFF)
    "last_esp32_relay_status": False  # Último estado reportado por el ESP32
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/datos', methods=['POST'])
def recibir_datos():
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No JSON payload received"}), 400

    temperatura = float(data.get('temperatura', 0))
    presion = float(data.get('presion', 0))
    altitud = float(data.get('altitud', 0))
    relay_activo = bool(data.get('relay_activo', False))
    co2 = float(data.get('co2', 400.0))
    humo = float(data.get('humo', 0.0))
    humedad_suelo = float(data.get('humedad_suelo', 0.0))

    # Actualizar estado del relé reportado
    relay_state["last_esp32_relay_status"] = relay_activo

    # Guardar en la base de datos a través de la clase Database
    try:
        db.save_reading(temperatura, presion, altitud, relay_activo, co2, humo, humedad_suelo)
    except Exception as e:
        print(f"Error guardando datos en la BD: {e}")

    # Determinar el comando y el modo a enviar al ESP32
    if relay_state["manual_mode"]:
        mode_str = "manual"
        comando = "ON" if relay_state["manual_state"] else "OFF"
    else:
        mode_str = "auto"
        comando = "OFF" # No relevante en modo auto

    return jsonify({
        "status": "ok",
        "mode": mode_str,
        "relay_command": comando
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    try:
        rows = db.get_history(limit=50)
        history_list = []
        for r in rows:
            history_list.append({
                "timestamp": r[0].split(" ")[1] if " " in r[0] else r[0], # Solo la hora para el eje X
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

    return jsonify({
        "history": history_list,
        "relay_state": relay_state
    })

@app.route('/api/relay/toggle', methods=['POST'])
def toggle_relay():
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No JSON payload received"}), 400

    if "manual_mode" in data:
        relay_state["manual_mode"] = bool(data["manual_mode"])
    if "manual_state" in data:
        relay_state["manual_state"] = bool(data["manual_state"])

    return jsonify({
        "status": "ok",
        "relay_state": relay_state
    })

@app.route('/historial')
def historial():
    return render_template('historial.html')

@app.route('/api/history/dates', methods=['GET'])
def get_history_dates():
    try:
        dates = db.get_available_dates()
    except Exception as e:
        print(f"Error obteniendo fechas: {e}")
        dates = []
    return jsonify(dates)

@app.route('/api/history/daily', methods=['GET'])
def get_daily_history():
    date_str = request.args.get('date')
    if not date_str:
        # Usar la fecha de hoy por defecto si no se pasa
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        
    try:
        history = db.get_daily_data(date_str)
        stats = db.get_daily_stats(date_str)
    except Exception as e:
        print(f"Error obteniendo datos diarios: {e}")
        history = []
        stats = {}
        
    return jsonify({
        "date": date_str,
        "history": history,
        "stats": stats
    })

if __name__ == '__main__':
    # Escucha en todas las interfaces de red en el puerto 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
