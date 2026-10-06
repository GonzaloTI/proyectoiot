import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class Database:
    def __init__(self, db_name='datos.db'):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        
        # 1. Tablas independientes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rol (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rol TEXT NOT NULL,
                descripcion TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS permisos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT NOT NULL,
                permiso TEXT NOT NULL,
                descripcion TEXT,
                estado INTEGER DEFAULT 1
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dispositivo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                modelo TEXT,
                mac TEXT UNIQUE,
                serial TEXT UNIQUE
            )
        ''')

        # 2. Tabla de Usuario
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                estado INTEGER DEFAULT 1,
                id_dispositivo INTEGER,
                FOREIGN KEY (id_dispositivo) REFERENCES dispositivo(id)
            )
        ''')

        # 3. Tablas Intermedias
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuario_rol (
                id_usuario INTEGER NOT NULL,
                id_rol INTEGER NOT NULL,
                PRIMARY KEY (id_usuario, id_rol),
                FOREIGN KEY (id_usuario) REFERENCES usuario(id) ON DELETE CASCADE,
                FOREIGN KEY (id_rol) REFERENCES rol(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuario_permiso (
                id_usuario INTEGER NOT NULL,
                id_permiso INTEGER NOT NULL,
                fechainicio DATETIME,
                fechafinal DATETIME,
                PRIMARY KEY (id_usuario, id_permiso),
                FOREIGN KEY (id_usuario) REFERENCES usuario(id) ON DELETE CASCADE,
                FOREIGN KEY (id_permiso) REFERENCES permisos(id) ON DELETE CASCADE
            )
        ''')

        # 4. Tabla de Suscripción
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS suscripcion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_usuario INTEGER UNIQUE NOT NULL,
                endpoint TEXT UNIQUE NOT NULL,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                FOREIGN KEY (id_usuario) REFERENCES usuario(id) ON DELETE CASCADE
            )
        ''')

        # 5. Tabla de Lecturas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_dispositivo INTEGER,
                timestamp DATETIME DEFAULT (datetime('now', 'localtime')),
                temperatura REAL,
                presion REAL,
                altitud REAL,
                relay_activo INTEGER,
                co2 REAL,
                humo REAL,
                humedad_suelo REAL,
                FOREIGN KEY (id_dispositivo) REFERENCES dispositivo(id) ON DELETE CASCADE
            )
        ''')
        
        # Verificar e incorporar las nuevas columnas si la tabla ya existía
        cursor.execute("PRAGMA table_info(readings)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'co2' not in columns:
            cursor.execute("ALTER TABLE readings ADD COLUMN co2 REAL")
        if 'humo' not in columns:
            cursor.execute("ALTER TABLE readings ADD COLUMN humo REAL")
        if 'humedad_suelo' not in columns:
            cursor.execute("ALTER TABLE readings ADD COLUMN humedad_suelo REAL")
        if 'id_dispositivo' not in columns:
            cursor.execute("ALTER TABLE readings ADD COLUMN id_dispositivo INTEGER")
            
        # 1. Crear roles por defecto si la tabla rol está vacía
        cursor.execute("SELECT COUNT(*) FROM rol")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO rol (rol, descripcion) VALUES (?, ?)", ("Admin", "Administrador del sistema con acceso total"))
            cursor.execute("INSERT INTO rol (rol, descripcion) VALUES (?, ?)", ("Operador", "Operador de monitoreo e historial"))

        # 2. Crear usuario administrador por defecto si la tabla usuario está vacía
        cursor.execute("SELECT id FROM usuario WHERE usuario = 'admin'")
        admin_row = cursor.fetchone()
        if not admin_row:
            default_pwd = generate_password_hash("admin123")
            cursor.execute(
                "INSERT INTO usuario (usuario, password, estado) VALUES (?, ?, ?)",
                ("admin", default_pwd, 1)
            )
            admin_id = cursor.lastrowid
        else:
            admin_id = admin_row[0]

        # 3. Asignar rol Admin al usuario admin por defecto si no lo tiene asignado
        cursor.execute("SELECT id FROM rol WHERE rol = 'Admin'")
        admin_role_row = cursor.fetchone()
        if admin_role_row and admin_id:
            admin_role_id = admin_role_row[0]
            cursor.execute("SELECT COUNT(*) FROM usuario_rol WHERE id_usuario = ? AND id_rol = ?", (admin_id, admin_role_id))
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO usuario_rol (id_usuario, id_rol) VALUES (?, ?)", (admin_id, admin_role_id))

        # 4. Crear los 6 permisos por defecto si la tabla permisos está vacía
        cursor.execute("SELECT COUNT(*) FROM permisos")
        if cursor.fetchone()[0] == 0:
            default_permisos = [
                ("CONTROL_RELE", "Controlar relés manualmente", "Permite encender y apagar los relés manualmente"),
                ("VER_HISTORIAL", "Ver historial de lecturas", "Permite consultar el historial de mediciones de sensores"),
                ("CREAR_USUARIOS", "Crear usuarios", "Permite registrar nuevos usuarios en el sistema"),
                ("CREAR_ROLES", "Crear roles", "Permite definir nuevos roles de usuario"),
                ("MODIFICAR_PERMISOS", "Modificar permisos", "Permite asignar o remover permisos a cualquier usuario"),
                ("DESACTIVAR_USUARIOS", "Desactivar usuarios", "Permite activar o suspender cuentas de usuario")
            ]
            for cod, perm, desc in default_permisos:
                cursor.execute("INSERT INTO permisos (codigo, permiso, descripcion, estado) VALUES (?, ?, ?, 1)", (cod, perm, desc))

        # 5. Asignar todos los permisos al usuario admin por defecto de forma indefinida (fechafinal = NULL)
        if admin_id:
            cursor.execute("SELECT id FROM permisos")
            all_perm_ids = [p[0] for p in cursor.fetchall()]
            for pid in all_perm_ids:
                cursor.execute("SELECT COUNT(*) FROM usuario_permiso WHERE id_usuario = ? AND id_permiso = ?", (admin_id, pid))
                if cursor.fetchone()[0] == 0:
                    cursor.execute(
                        "INSERT INTO usuario_permiso (id_usuario, id_permiso, fechainicio, fechafinal) VALUES (?, ?, datetime('now', 'localtime'), NULL)",
                        (admin_id, pid)
                    )
            
        conn.commit()
        conn.close()

    def save_reading(self, temperatura, presion, altitud, relay_activo, co2, humo, humedad_suelo, id_dispositivo=None):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO readings (temperatura, presion, altitud, relay_activo, co2, humo, humedad_suelo, id_dispositivo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (temperatura, presion, altitud, 1 if relay_activo else 0, co2, humo, humedad_suelo, id_dispositivo)
        )
        conn.commit()
        conn.close()

    def get_history(self, limit=50):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT timestamp, temperatura, presion, altitud, relay_activo, co2, humo, humedad_suelo FROM readings ORDER BY id DESC LIMIT ?',
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
                   AVG(humo) as avg_humo,
                   AVG(humedad_suelo) as avg_humedad_suelo
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
            "humo": round(r[6], 1) if r[6] is not None else 0,
            "humedad_suelo": round(r[7], 1) if r[7] is not None else 0
        } for r in rows]

    def get_daily_stats(self, date_str):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT timestamp, temperatura, presion, altitud, relay_activo, co2, humo, humedad_suelo FROM readings 
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
                "humo_min": 0, "humo_max": 0, "humo_avg": 0,
                "humedad_suelo_min": 0, "humedad_suelo_max": 0, "humedad_suelo_avg": 0
            }
        
        # Calcular tiempo activo del relé
        active_seconds = 0
        for i in range(len(rows) - 1):
            t1_str, _, _, _, active1, _, _, _ = rows[i]
            t2_str, _, _, _, active2, _, _, _ = rows[i+1]
            
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
        humedades = [r[7] for r in rows if len(r) > 7 and r[7] is not None]
        
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
            "humo_avg": round(sum(humos)/len(humos), 1) if humos else 0,
            "humedad_suelo_min": round(min(humedades), 1) if humedades else 0,
            "humedad_suelo_max": round(max(humedades), 1) if humedades else 0,
            "humedad_suelo_avg": round(sum(humedades)/len(humedades), 1) if humedades else 0
        }

    # ==================== MÉTODOS DE ROLES Y USUARIOS ====================

    def get_roles(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id, rol, descripcion FROM rol ORDER BY id ASC')
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r[0], "rol": r[1], "descripcion": r[2]} for r in rows]

    def create_role(self, rol_name, descripcion=""):
        rol_name = rol_name.strip()
        if not rol_name:
            return None, "El nombre del rol es obligatorio."
        if len(rol_name) > 40:
            return None, "El nombre del rol no debe superar los 40 caracteres."
            
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO rol (rol, descripcion) VALUES (?, ?)', (rol_name, descripcion))
            conn.commit()
            new_id = cursor.lastrowid
            return new_id, None
        except sqlite3.IntegrityError:
            return None, "El rol ya existe."
        finally:
            conn.close()

    def get_user_roles(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.id, r.rol, r.descripcion 
            FROM rol r
            JOIN usuario_rol ur ON r.id = ur.id_rol
            WHERE ur.id_usuario = ?
        ''', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r[0], "rol": r[1], "descripcion": r[2]} for r in rows]

    def get_all_users(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id, usuario, estado, id_dispositivo FROM usuario ORDER BY id ASC')
        users_rows = cursor.fetchall()
        conn.close()
        
        users_list = []
        for u in users_rows:
            user_id = u[0]
            roles_list = self.get_user_roles(user_id)
            user_perms = self.get_user_permissions(user_id)
            
            users_list.append({
                "id": user_id,
                "usuario": u[1],
                "estado": bool(u[2]),
                "id_dispositivo": u[3],
                "roles": roles_list,
                "permissions": user_perms
            })
            
        return users_list

    def create_user(self, usuario, password, estado=1, id_dispositivo=None, role_ids=None):
        if not usuario or not password:
            return None, "Usuario y contraseña son requeridos."
        if len(usuario) > 40:
            return None, "El nombre de usuario no puede superar los 40 caracteres."
        if len(password) > 40:
            return None, "La contraseña no puede superar los 40 caracteres."
            
        pwd_hash = generate_password_hash(password)
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO usuario (usuario, password, estado, id_dispositivo) VALUES (?, ?, ?, ?)',
                (usuario, pwd_hash, 1 if estado else 0, id_dispositivo)
            )
            user_id = cursor.lastrowid
            
            # Asignar roles si se especificaron
            if role_ids:
                for rid in role_ids:
                    cursor.execute(
                        'INSERT INTO usuario_rol (id_usuario, id_rol) VALUES (?, ?)',
                        (user_id, int(rid))
                    )
                    
            conn.commit()
            return user_id, None
        except sqlite3.IntegrityError:
            return None, "El nombre de usuario ya existe."
        finally:
            conn.close()

    def toggle_user_status(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT estado FROM usuario WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        if row:
            new_status = 0 if row[0] else 1
            cursor.execute('UPDATE usuario SET estado = ? WHERE id = ?', (new_status, user_id))
            conn.commit()
            conn.close()
            return new_status
        conn.close()
        return None

    def get_user_by_username(self, usuario):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id, usuario, password, estado, id_dispositivo FROM usuario WHERE usuario = ?', (usuario,))
        row = cursor.fetchone()
        conn.close()
        if row:
            roles = self.get_user_roles(row[0])
            return {
                "id": row[0],
                "usuario": row[1],
                "password": row[2],
                "estado": row[3],
                "id_dispositivo": row[4],
                "roles": [r["rol"] for r in roles]
            }
        return None

    def verify_user_credentials(self, usuario, password):
        if not usuario or not password:
            return None, "Debe ingresar usuario y contraseña."
        if len(usuario) > 40:
            return None, "El usuario no puede superar los 40 caracteres."
        if len(password) > 40:
            return None, "La contraseña no puede superar los 40 caracteres."
            
        user = self.get_user_by_username(usuario)
        if not user:
            return None, "Usuario o contraseña incorrectos."
            
        if not user["estado"]:
            return None, "La cuenta de usuario se encuentra inactiva."
            
        pwd_db = user["password"]
        valid = False
        if pwd_db.startswith("pbkdf2:") or pwd_db.startswith("scrypt:") or pwd_db.startswith("argon2:"):
            valid = check_password_hash(pwd_db, password)
        else:
            valid = (pwd_db == password)
            
        if valid:
            return user, None
        return None, "Usuario o contraseña incorrectos."

    # ==================== MÉTODOS DE GESTIÓN DE PERMISOS ====================

    def get_all_permissions(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id, codigo, permiso, descripcion, estado FROM permisos ORDER BY id ASC')
        rows = cursor.fetchall()
        conn.close()
        return [{
            "id": r[0],
            "codigo": r[1],
            "permiso": r[2],
            "descripcion": r[3],
            "estado": bool(r[4])
        } for r in rows]

    def get_user_permissions(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.id, p.codigo, p.permiso, p.descripcion, up.fechainicio, up.fechafinal
            FROM permisos p
            JOIN usuario_permiso up ON p.id = up.id_permiso
            WHERE up.id_usuario = ? AND p.estado = 1
        ''', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        perms = {}
        for r in rows:
            fechafinal = r[5]
            is_valid = True
            if fechafinal and len(str(fechafinal).strip()) > 0:
                try:
                    dt_final = datetime.strptime(str(fechafinal)[:10], "%Y-%m-%d")
                    dt_now = datetime.now()
                    if dt_final.date() < dt_now.date():
                        is_valid = False
                except Exception:
                    pass
            
            perms[r[1]] = {
                "id": r[0],
                "codigo": r[1],
                "permiso": r[2],
                "descripcion": r[3],
                "fechainicio": r[4],
                "fechafinal": r[5] if fechafinal else None,
                "is_indefinite": (not fechafinal or str(fechafinal).strip() == ""),
                "is_valid": is_valid
            }
        return perms

    def user_has_permission(self, user_id, codigo_permiso):
        if not user_id:
            return False
        # Si el usuario es Admin, posee todos los permisos automáticamente
        roles = self.get_user_roles(user_id)
        if any(r["rol"] == "Admin" for r in roles):
            return True
            
        user_perms = self.get_user_permissions(user_id)
        if codigo_permiso in user_perms:
            return user_perms[codigo_permiso]["is_valid"]
        return False

    def update_user_permissions(self, user_id, permissions_dict):
        """
        permissions_dict: dict key=permiso_id (int or str), value=fechafinal (str YYYY-MM-DD or None)
        """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Eliminar permisos anteriores
        cursor.execute('DELETE FROM usuario_permiso WHERE id_usuario = ?', (user_id,))
        
        # Insertar los permisos seleccionados
        for perm_id, fechafinal in permissions_dict.items():
            ff = fechafinal.strip() if (fechafinal and isinstance(fechafinal, str) and str(fechafinal).strip() != "") else None
            cursor.execute(
                '''INSERT INTO usuario_permiso (id_usuario, id_permiso, fechainicio, fechafinal) 
                   VALUES (?, ?, datetime('now', 'localtime'), ?)''',
                (user_id, int(perm_id), ff)
            )
            
        conn.commit()
        conn.close()
            
    def update_user(self, user_id, new_password=None, role_ids=None):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # 1. Actualizar contraseña si se proporcionó una nueva
        if new_password and new_password.strip():
            pwd_clean = new_password.strip()
            if len(pwd_clean) > 40:
                conn.close()
                return False, "La contraseña no debe exceder los 40 caracteres."
            pwd_hash = generate_password_hash(pwd_clean)
            cursor.execute('UPDATE usuario SET password = ? WHERE id = ?', (pwd_hash, user_id))

        # 2. Actualizar roles si se pasó la lista
        if role_ids is not None:
            cursor.execute('DELETE FROM usuario_rol WHERE id_usuario = ?', (user_id,))
            for rid in role_ids:
                cursor.execute('INSERT INTO usuario_rol (id_usuario, id_rol) VALUES (?, ?)', (user_id, int(rid)))

        conn.commit()
        conn.close()
        return True, None


