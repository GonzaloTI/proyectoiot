import sqlite3
from datetime import datetime

class Database:
    def __init__(self, db_name='datos.db'):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT (datetime('now', 'localtime')),
                temperatura REAL,
                presion REAL,
                altitud REAL,
                relay_activo INTEGER,
                co2 REAL,
                humo REAL
            )
        ''')
        
        # Verificar e incorporar las nuevas columnas si la tabla ya existía
        cursor.execute("PRAGMA table_info(readings)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'co2' not in columns:
            cursor.execute("ALTER TABLE readings ADD COLUMN co2 REAL")
        if 'humo' not in columns:
            cursor.execute("ALTER TABLE readings ADD COLUMN humo REAL")
            
        conn.commit()
        conn.close()

    def save_reading(self, temperatura, presion, altitud, relay_activo, co2, humo):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO readings (temperatura, presion, altitud, relay_activo, co2, humo) VALUES (?, ?, ?, ?, ?, ?)',
            (temperatura, presion, altitud, 1 if relay_activo else 0, co2, humo)
        )
        conn.commit()
        conn.close()

    def get_history(self, limit=50):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT timestamp, temperatura, presion, altitud, relay_activo, co2, humo FROM readings ORDER BY id DESC LIMIT ?',
            (limit,)
        )
        rows = cursor.fetchall()
        conn.close()
        # Voltear el orden para tenerlo de más viejo a más nuevo en el gráfico
        rows.reverse()
        return rows

    def get_available_dates(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT date(timestamp) FROM readings ORDER BY date(timestamp) DESC')
        dates = [row[0] for row in cursor.fetchall()]
        conn.close()
        return dates

    def get_daily_data(self, date_str):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        # Agrupar por minuto para reducir puntos y mejorar velocidad de carga
        cursor.execute('''
            SELECT strftime('%H:%M', timestamp) as time_label, 
                   AVG(temperatura) as avg_temp, 
                   AVG(presion) as avg_pres, 
                   AVG(altitud) as avg_alt, 
                   MAX(relay_activo) as max_relay,
                   AVG(co2) as avg_co2,
                   AVG(humo) as avg_humo
            FROM readings 
            WHERE date(timestamp) = ? 
            GROUP BY time_label 
            ORDER BY time_label ASC
        ''', (date_str,))
        rows = cursor.fetchall()
        conn.close()
        
        return [{
            "time": r[0],
            "temperatura": round(r[1], 2) if r[1] is not None else 0,
            "presion": round(r[2], 2) if r[2] is not None else 0,
            "altitud": round(r[3], 2) if r[3] is not None else 0,
            "relay_activo": bool(r[4]),
            "co2": round(r[5], 1) if r[5] is not None else 0,
            "humo": round(r[6], 1) if r[6] is not None else 0
        } for r in rows]

    def get_daily_stats(self, date_str):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT timestamp, temperatura, presion, altitud, relay_activo, co2, humo FROM readings 
            WHERE date(timestamp) = ? 
            ORDER BY id ASC
        ''', (date_str,))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return {
                "total_readings": 0,
                "active_time_str": "0s",
                "temp_min": 0, "temp_max": 0, "temp_avg": 0,
                "pres_min": 0, "pres_max": 0, "pres_avg": 0,
                "alt_min": 0, "alt_max": 0, "alt_avg": 0,
                "co2_min": 0, "co2_max": 0, "co2_avg": 0,
                "humo_min": 0, "humo_max": 0, "humo_avg": 0
            }
        
        # Calcular tiempo activo del relé
        active_seconds = 0
        for i in range(len(rows) - 1):
            t1_str, _, _, _, active1, _, _ = rows[i]
            t2_str, _, _, _, active2, _, _ = rows[i+1]
            
            if active1:
                try:
                    dt1 = datetime.strptime(t1_str, "%Y-%m-%d %H:%M:%S")
                    dt2 = datetime.strptime(t2_str, "%Y-%m-%d %H:%M:%S")
                    diff = (dt2 - dt1).total_seconds()
                    if diff < 10:
                        active_seconds += diff
                    else:
                        active_seconds += 2
                except:
                    active_seconds += 2
        if rows[-1][4]: # Última lectura activa
            active_seconds += 2
            
        # Formatear el tiempo activo
        hours = int(active_seconds // 3600)
        minutes = int((active_seconds % 3600) // 60)
        seconds = int(active_seconds % 60)
        formatted = ""
        if hours > 0: formatted += f"{hours}h "
        if minutes > 0 or hours > 0: formatted += f"{minutes}m "
        formatted += f"{seconds}s"
        
        # Extraer valores para min/max/promedio
        temps = [r[1] for r in rows if r[1] is not None]
        pres = [r[2] for r in rows if r[2] is not None]
        alts = [r[3] for r in rows if r[3] is not None]
        co2s = [r[5] for r in rows if r[5] is not None]
        humos = [r[6] for r in rows if r[6] is not None]
        
        return {
            "total_readings": len(rows),
            "active_time_str": formatted,
            "temp_min": round(min(temps), 1) if temps else 0,
            "temp_max": round(max(temps), 1) if temps else 0,
            "temp_avg": round(sum(temps)/len(temps), 1) if temps else 0,
            "pres_min": round(min(pres), 1) if pres else 0,
            "pres_max": round(max(pres), 1) if pres else 0,
            "pres_avg": round(sum(pres)/len(pres), 1) if pres else 0,
            "alt_min": round(min(alts), 1) if alts else 0,
            "alt_max": round(max(alts), 1) if alts else 0,
            "alt_avg": round(sum(alts)/len(alts), 1) if alts else 0,
            "co2_min": round(min(co2s), 1) if co2s else 0,
            "co2_max": round(max(co2s), 1) if co2s else 0,
            "co2_avg": round(sum(co2s)/len(co2s), 1) if co2s else 0,
            "humo_min": round(min(humos), 1) if humos else 0,
            "humo_max": round(max(humos), 1) if humos else 0,
            "humo_avg": round(sum(humos)/len(humos), 1) if humos else 0
        }
