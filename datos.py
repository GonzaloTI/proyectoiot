import os
import psycopg2
import psycopg2.extras
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

class Database:
    def __init__(self, db_name='postgres', **kwargs):
        """
        Inicializa la conexión hacia PostgreSQL / Supabase utilizando variables de entorno
        o los parámetros proporcionados por defecto.
        """
        self.host = os.getenv("DB_HOST", "db.rgjsddiqrgpelenvxfdu.supabase.co")
        self.port = int(os.getenv("DB_PORT", "5432"))
        
        # Si se pasa un nombre de archivo SQLite antiguo (.db), usar la base de datos postgres
        env_dbname = os.getenv("DB_NAME")
        if env_dbname:
            self.dbname = env_dbname
        elif not db_name or db_name.endswith('.db'):
            self.dbname = "postgres"
        else:
            self.dbname = db_name

        self.user = os.getenv("DB_USER", "postgres")
        self.password = os.getenv("DB_PASSWORD") or os.getenv("pass_varios", "")
        self.sslmode = os.getenv("DB_SSLMODE", "require")
        
        try:
            self.init_db()
        except Exception as e:
            print(f"⚠️ [Supabase DB] Advertencia al inicializar tablas: {e}")

    def get_connection(self):
        """
        Crea y retorna una nueva conexión hacia PostgreSQL Supabase.
        """
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.user,
            password=self.password,
            sslmode=self.sslmode,
            connect_timeout=10
        )

    def init_db(self):
        """
        Crea las tablas y datos por defecto (roles, permisos, usuario admin) en Supabase si no existen.
        """
        try:
            conn = self.get_connection()
        except Exception as e:
            print(f"⚠️ [Supabase DB] No se pudo conectar en init_db(): {e}")
            return

        cursor = conn.cursor()
        try:
            # 1. Tablas independientes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rol (
                    id SERIAL PRIMARY KEY,
                    rol VARCHAR(100) NOT NULL,
                    descripcion TEXT
                );
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS permisos (
                    id SERIAL PRIMARY KEY,
                    codigo VARCHAR(100) NOT NULL UNIQUE,
                    permiso VARCHAR(200) NOT NULL,
                    descripcion TEXT,
                    estado INTEGER DEFAULT 1
                );
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dispositivo (
                    id SERIAL PRIMARY KEY,
                    nombre VARCHAR(100),
                    modelo VARCHAR(100),
                    mac VARCHAR(100) UNIQUE,
                    serial VARCHAR(100) UNIQUE
                );
            ''')

            # 2. Tabla de Usuario
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuario (
                    id SERIAL PRIMARY KEY,
                    usuario VARCHAR(100) UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    estado INTEGER DEFAULT 1,
                    id_dispositivo INTEGER,
                    FOREIGN KEY (id_dispositivo) REFERENCES dispositivo(id) ON DELETE SET NULL
                );
            ''')

            # 3. Tablas Intermedias
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuario_rol (
                    id_usuario INTEGER NOT NULL,
                    id_rol INTEGER NOT NULL,
                    PRIMARY KEY (id_usuario, id_rol),
                    FOREIGN KEY (id_usuario) REFERENCES usuario(id) ON DELETE CASCADE,
                    FOREIGN KEY (id_rol) REFERENCES rol(id) ON DELETE CASCADE
                );
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuario_permiso (
                    id_usuario INTEGER NOT NULL,
                    id_permiso INTEGER NOT NULL,
                    fechainicio TIMESTAMP,
                    fechafinal TIMESTAMP,
                    PRIMARY KEY (id_usuario, id_permiso),
                    FOREIGN KEY (id_usuario) REFERENCES usuario(id) ON DELETE CASCADE,
                    FOREIGN KEY (id_permiso) REFERENCES permisos(id) ON DELETE CASCADE
                );
            ''')

            # 4. Tabla de Suscripción Web Push
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS suscripcion (
                    id SERIAL PRIMARY KEY,
                    id_usuario INTEGER UNIQUE NOT NULL,
                    endpoint TEXT UNIQUE NOT NULL,
                    p256dh TEXT NOT NULL,
                    auth TEXT NOT NULL,
                    FOREIGN KEY (id_usuario) REFERENCES usuario(id) ON DELETE CASCADE
                );
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id SERIAL PRIMARY KEY,
                    endpoint TEXT UNIQUE NOT NULL,
                    p256dh TEXT NOT NULL,
                    auth TEXT NOT NULL
                );
            ''')

            # 5. Tabla de Lecturas de Sensores
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS readings (
                    id SERIAL PRIMARY KEY,
                    id_dispositivo INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    temperatura REAL,
                    presion REAL,
                    altitud REAL,
                    relay_activo INTEGER,
                    co2 REAL,
                    humo REAL,
                    humedad_suelo REAL,
                    FOREIGN KEY (id_dispositivo) REFERENCES dispositivo(id) ON DELETE CASCADE
                );
            ''')

            # 6. Tabla de Detecciones (Visión Artificial Fragaria)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS detecciones (
                    id SERIAL PRIMARY KEY,
                    path TEXT NOT NULL,
                    modelo VARCHAR(100) NOT NULL,
                    total INTEGER NOT NULL,
                    clase VARCHAR(100) NOT NULL,
                    conf REAL NOT NULL,
                    enfermedad INTEGER NOT NULL,
                    fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            ''')

            # Roles por defecto
            cursor.execute("SELECT COUNT(*) FROM rol")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO rol (rol, descripcion) VALUES (%s, %s)", ("Admin", "Administrador del sistema con acceso total"))
                cursor.execute("INSERT INTO rol (rol, descripcion) VALUES (%s, %s)", ("Operador", "Operador de monitoreo e historial"))

            # Usuario administrador por defecto
            cursor.execute("SELECT id FROM usuario WHERE usuario = %s", ("admin",))
            admin_row = cursor.fetchone()
            if not admin_row:
                default_pwd = generate_password_hash("admin123")
                cursor.execute(
                    "INSERT INTO usuario (usuario, password, estado) VALUES (%s, %s, %s) RETURNING id",
                    ("admin", default_pwd, 1)
                )
                admin_id = cursor.fetchone()[0]
            else:
                admin_id = admin_row[0]

            # Rol Admin para usuario admin
            cursor.execute("SELECT id FROM rol WHERE rol = %s", ("Admin",))
            admin_role_row = cursor.fetchone()
            if admin_role_row and admin_id:
                admin_role_id = admin_role_row[0]
                cursor.execute("SELECT COUNT(*) FROM usuario_rol WHERE id_usuario = %s AND id_rol = %s", (admin_id, admin_role_id))
                if cursor.fetchone()[0] == 0:
                    cursor.execute("INSERT INTO usuario_rol (id_usuario, id_rol) VALUES (%s, %s)", (admin_id, admin_role_id))

            # Permisos por defecto
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
                    cursor.execute(
                        "INSERT INTO permisos (codigo, permiso, descripcion, estado) VALUES (%s, %s, %s, 1) ON CONFLICT (codigo) DO NOTHING",
                        (cod, perm, desc)
                    )

            # Asignar permisos al admin
            if admin_id:
                cursor.execute("SELECT id FROM permisos")
                all_perm_ids = [p[0] for p in cursor.fetchall()]
                for pid in all_perm_ids:
                    cursor.execute("SELECT COUNT(*) FROM usuario_permiso WHERE id_usuario = %s AND id_permiso = %s", (admin_id, pid))
                    if cursor.fetchone()[0] == 0:
                        cursor.execute(
                            "INSERT INTO usuario_permiso (id_usuario, id_permiso, fechainicio, fechafinal) VALUES (%s, %s, NOW(), NULL)",
                            (admin_id, pid)
                        )

            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"⚠️ [Supabase DB] Error en init_db(): {e}")
        finally:
            cursor.close()
            conn.close()

    def save_reading(self, temperatura, presion, altitud, relay_activo, co2, humo, humedad_suelo, id_dispositivo=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                '''INSERT INTO readings (temperatura, presion, altitud, relay_activo, co2, humo, humedad_suelo, id_dispositivo) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                (temperatura, presion, altitud, 1 if relay_activo else 0, co2, humo, humedad_suelo, id_dispositivo)
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def get_history(self, limit=50):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                '''SELECT timestamp, temperatura, presion, altitud, relay_activo, co2, humo, humedad_suelo 
                   FROM readings ORDER BY id DESC LIMIT %s''',
                (limit,)
            )
            raw_rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

        # Formatear timestamp como cadena para compatibilidad completa
        rows = []
        for r in raw_rows:
            ts = r[0].strftime("%Y-%m-%d %H:%M:%S") if hasattr(r[0], 'strftime') else str(r[0])
            rows.append((ts, r[1], r[2], r[3], r[4], r[5], r[6], r[7]))

        # Voltear el orden para tenerlo de más viejo a más nuevo en el gráfico
        rows.reverse()
        return rows

    def get_available_dates(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT DISTINCT TO_CHAR(timestamp, 'YYYY-MM-DD') as fecha FROM readings ORDER BY fecha DESC")
            dates = [str(row[0]) for row in cursor.fetchall() if row[0]]
        finally:
            cursor.close()
            conn.close()
        return dates

    def get_daily_data(self, date_str):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Agrupar por minuto para reducir puntos y mejorar velocidad de carga
            cursor.execute('''
                SELECT TO_CHAR(timestamp, 'HH24:MI') as time_label, 
                       AVG(temperatura) as avg_temp, 
                       AVG(presion) as avg_pres, 
                       AVG(altitud) as avg_alt, 
                       MAX(relay_activo) as max_relay,
                       AVG(co2) as avg_co2,
                       AVG(humo) as avg_humo,
                       AVG(humedad_suelo) as avg_humedad_suelo
                FROM readings 
                WHERE DATE(timestamp) = %s::date 
                GROUP BY time_label 
                ORDER BY time_label ASC
            ''', (date_str,))
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

        return [{
            "time": r[0],
            "temperatura": round(float(r[1]), 2) if r[1] is not None else 0,
            "presion": round(float(r[2]), 2) if r[2] is not None else 0,
            "altitud": round(float(r[3]), 2) if r[3] is not None else 0,
            "relay_activo": bool(r[4]),
            "co2": round(float(r[5]), 1) if r[5] is not None else 0,
            "humo": round(float(r[6]), 1) if r[6] is not None else 0,
            "humedad_suelo": round(float(r[7]), 1) if r[7] is not None else 0
        } for r in rows]

    def get_daily_stats(self, date_str):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT timestamp, temperatura, presion, altitud, relay_activo, co2, humo, humedad_suelo 
                FROM readings 
                WHERE DATE(timestamp) = %s::date 
                ORDER BY id ASC
            ''', (date_str,))
            rows = cursor.fetchall()
        finally:
            cursor.close()
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
            t1_val, _, _, _, active1, _, _, _ = rows[i]
            t2_val, _, _, _, active2, _, _, _ = rows[i+1]

            if active1:
                try:
                    dt1 = t1_val if isinstance(t1_val, datetime) else datetime.strptime(str(t1_val)[:19], "%Y-%m-%d %H:%M:%S")
                    dt2 = t2_val if isinstance(t2_val, datetime) else datetime.strptime(str(t2_val)[:19], "%Y-%m-%d %H:%M:%S")
                    diff = (dt2 - dt1).total_seconds()
                    if diff < 10:
                        active_seconds += diff
                    else:
                        active_seconds += 2
                except Exception:
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
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id, rol, descripcion FROM rol ORDER BY id ASC')
            rows = cursor.fetchall()
            return [{"id": r[0], "rol": r[1], "descripcion": r[2]} for r in rows]
        finally:
            cursor.close()
            conn.close()

    def create_role(self, rol_name, descripcion=""):
        rol_name = rol_name.strip()
        if not rol_name:
            return None, "El nombre del rol es obligatorio."
        if len(rol_name) > 40:
            return None, "El nombre del rol no debe superar los 40 caracteres."

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO rol (rol, descripcion) VALUES (%s, %s) RETURNING id', (rol_name, descripcion))
            new_id = cursor.fetchone()[0]
            conn.commit()
            return new_id, None
        except psycopg2.IntegrityError:
            conn.rollback()
            return None, "El rol ya existe."
        except Exception as e:
            conn.rollback()
            return None, str(e)
        finally:
            cursor.close()
            conn.close()

    def get_user_roles(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT r.id, r.rol, r.descripcion 
                FROM rol r
                JOIN usuario_rol ur ON r.id = ur.id_rol
                WHERE ur.id_usuario = %s
            ''', (user_id,))
            rows = cursor.fetchall()
            return [{"id": r[0], "rol": r[1], "descripcion": r[2]} for r in rows]
        finally:
            cursor.close()
            conn.close()

    def get_all_users(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id, usuario, estado, id_dispositivo FROM usuario ORDER BY id ASC')
            users_rows = cursor.fetchall()
        finally:
            cursor.close()
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
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO usuario (usuario, password, estado, id_dispositivo) VALUES (%s, %s, %s, %s) RETURNING id',
                (usuario, pwd_hash, 1 if estado else 0, id_dispositivo)
            )
            user_id = cursor.fetchone()[0]

            # Asignar roles si se especificaron
            if role_ids:
                for rid in role_ids:
                    cursor.execute(
                        'INSERT INTO usuario_rol (id_usuario, id_rol) VALUES (%s, %s)',
                        (user_id, int(rid))
                    )

            conn.commit()
            return user_id, None
        except psycopg2.IntegrityError:
            conn.rollback()
            return None, "El nombre de usuario ya existe."
        except Exception as e:
            conn.rollback()
            return None, str(e)
        finally:
            cursor.close()
            conn.close()

    def toggle_user_status(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT estado FROM usuario WHERE id = %s', (user_id,))
            row = cursor.fetchone()
            if row:
                new_status = 0 if row[0] else 1
                cursor.execute('UPDATE usuario SET estado = %s WHERE id = %s', (new_status, user_id))
                conn.commit()
                return new_status
            return None
        finally:
            cursor.close()
            conn.close()

    def get_user_by_username(self, usuario):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id, usuario, password, estado, id_dispositivo FROM usuario WHERE usuario = %s', (usuario,))
            row = cursor.fetchone()
        finally:
            cursor.close()
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
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id, codigo, permiso, descripcion, estado FROM permisos ORDER BY id ASC')
            rows = cursor.fetchall()
            return [{
                "id": r[0],
                "codigo": r[1],
                "permiso": r[2],
                "descripcion": r[3],
                "estado": bool(r[4])
            } for r in rows]
        finally:
            cursor.close()
            conn.close()

    def get_user_permissions(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT p.id, p.codigo, p.permiso, p.descripcion, up.fechainicio, up.fechafinal
                FROM permisos p
                JOIN usuario_permiso up ON p.id = up.id_permiso
                WHERE up.id_usuario = %s AND p.estado = 1
            ''', (user_id,))
            rows = cursor.fetchall()
        finally:
            cursor.close()
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

            fechainicio_str = r[4].strftime("%Y-%m-%d %H:%M:%S") if hasattr(r[4], 'strftime') else (str(r[4]) if r[4] else None)
            fechafinal_str = r[5].strftime("%Y-%m-%d") if hasattr(r[5], 'strftime') else (str(r[5]) if r[5] else None)

            perms[r[1]] = {
                "id": r[0],
                "codigo": r[1],
                "permiso": r[2],
                "descripcion": r[3],
                "fechainicio": fechainicio_str,
                "fechafinal": fechafinal_str if fechafinal else None,
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
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Eliminar permisos anteriores
            cursor.execute('DELETE FROM usuario_permiso WHERE id_usuario = %s', (user_id,))

            # Insertar los permisos seleccionados
            for perm_id, fechafinal in permissions_dict.items():
                ff = fechafinal.strip() if (fechafinal and isinstance(fechafinal, str) and str(fechafinal).strip() != "") else None
                cursor.execute(
                    '''INSERT INTO usuario_permiso (id_usuario, id_permiso, fechainicio, fechafinal) 
                       VALUES (%s, %s, NOW(), %s)''',
                    (user_id, int(perm_id), ff)
                )

            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def update_user(self, user_id, new_password=None, role_ids=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # 1. Actualizar contraseña si se proporcionó una nueva
            if new_password and new_password.strip():
                pwd_clean = new_password.strip()
                if len(pwd_clean) > 40:
                    return False, "La contraseña no debe exceder los 40 caracteres."
                pwd_hash = generate_password_hash(pwd_clean)
                cursor.execute('UPDATE usuario SET password = %s WHERE id = %s', (pwd_hash, user_id))

            # 2. Actualizar roles si se pasó la lista
            if role_ids is not None:
                cursor.execute('DELETE FROM usuario_rol WHERE id_usuario = %s', (user_id,))
                for rid in role_ids:
                    cursor.execute('INSERT INTO usuario_rol (id_usuario, id_rol) VALUES (%s, %s)', (user_id, int(rid)))

            conn.commit()
            return True, None
        finally:
            cursor.close()
            conn.close()

    # ==================== MÉTODOS DE NOTIFICACIONES PUSH ====================
    def save_push_subscription(self, endpoint, p256dh, auth):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO subscriptions (endpoint, p256dh, auth)
                VALUES (%s, %s, %s)
                ON CONFLICT (endpoint) DO UPDATE 
                SET p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth
            """, (endpoint, p256dh, auth))
            conn.commit()
            cursor.execute("SELECT COUNT(*) FROM subscriptions")
            total = cursor.fetchone()[0]
            return total
        finally:
            cursor.close()
            conn.close()

    def get_push_subscriptions(self):
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            cursor.execute("SELECT * FROM subscriptions")
            rows = cursor.fetchall()
            return rows
        finally:
            cursor.close()
            conn.close()

    # =========================================================================
    # Métodos de Detecciones (Visión Artificial Fragaria)
    # =========================================================================
    def save_detection(self, path, modelo, total, clase, conf, enfermedad):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO detecciones (path, modelo, total, clase, conf, enfermedad, fecha_hora)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                RETURNING id
            ''', (path, modelo, int(total), clase, float(conf), 1 if enfermedad else 0))
            new_id = cursor.fetchone()[0]
            conn.commit()
            return new_id
        finally:
            cursor.close()
            conn.close()

    def get_latest_detection(self):
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute('''
                SELECT * FROM detecciones ORDER BY id DESC LIMIT 1
            ''')
            row = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

        if row:
            res = dict(row)
            res['enfermedad'] = bool(res['enfermedad'])
            if 'fecha_hora' in res and res['fecha_hora']:
                res['fecha_hora'] = res['fecha_hora'].strftime("%Y-%m-%d %H:%M:%S") if hasattr(res['fecha_hora'], 'strftime') else str(res['fecha_hora'])
            return res
        return None

    def get_detections_history(self, limit=50):
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute('''
                SELECT * FROM detecciones ORDER BY id DESC LIMIT %s
            ''', (limit,))
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

        result = []
        for r in rows:
            d = dict(r)
            d['enfermedad'] = bool(d['enfermedad'])
            if 'fecha_hora' in d and d['fecha_hora']:
                d['fecha_hora'] = d['fecha_hora'].strftime("%Y-%m-%d %H:%M:%S") if hasattr(d['fecha_hora'], 'strftime') else str(d['fecha_hora'])
            result.append(d)
        return result

    def get_detections_history_paginated(self, page=1, per_page=10, fecha_desde=None, fecha_hasta=None, clase=None, busqueda=None, sort_col=None, sort_dir=None):
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        conditions = []
        params = []

        if fecha_desde:
            conditions.append("DATE(fecha_hora) >= %s::date")
            params.append(fecha_desde)

        if fecha_hasta:
            conditions.append("DATE(fecha_hora) <= %s::date")
            params.append(fecha_hasta)

        if clase and clase != 'TODAS':
            conditions.append("clase = %s")
            params.append(clase)

        if busqueda and busqueda.strip():
            term = f"%{busqueda.strip()}%"
            conditions.append("(clase ILIKE %s OR modelo ILIKE %s OR CAST(id AS TEXT) LIKE %s OR CAST(fecha_hora AS TEXT) LIKE %s)")
            params.extend([term, term, term, term])

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        try:
            # 1. Conteo total con filtros
            count_sql = f"SELECT COUNT(*) as total FROM detecciones {where_clause}"
            cursor.execute(count_sql, params)
            total_records = cursor.fetchone()['total']

            # 2. Ordenamiento seguro
            valid_cols = {
                'id': 'id',
                'fecha_hora': 'fecha_hora',
                'modelo': 'modelo',
                'clase': 'clase',
                'conf': 'conf',
                'condicion': 'enfermedad'
            }

            if sort_col and sort_col in valid_cols:
                col_db = valid_cols[sort_col]
                dir_db = 'ASC' if str(sort_dir).upper() == 'ASC' else 'DESC'
                order_by = f"ORDER BY {col_db} {dir_db}, id DESC"
            else:
                # Orden natural: más recientes primero
                order_by = "ORDER BY id DESC"

            # 3. Paginación
            try:
                page = max(1, int(page))
            except (ValueError, TypeError):
                page = 1

            try:
                per_page = max(1, min(100, int(per_page)))
            except (ValueError, TypeError):
                per_page = 10

            offset = (page - 1) * per_page

            query_sql = f"""
                SELECT * FROM detecciones
                {where_clause}
                {order_by}
                LIMIT %s OFFSET %s
            """
            cursor.execute(query_sql, params + [per_page, offset])
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

        result = []
        for r in rows:
            d = dict(r)
            d['enfermedad'] = bool(d['enfermedad'])
            if 'fecha_hora' in d and d['fecha_hora']:
                d['fecha_hora'] = d['fecha_hora'].strftime("%Y-%m-%d %H:%M:%S") if hasattr(d['fecha_hora'], 'strftime') else str(d['fecha_hora'])
            result.append(d)

        total_pages = (total_records + per_page - 1) // per_page if total_records > 0 else 1

        return {
            "detecciones": result,
            "total_registros": total_records,
            "total_paginas": total_pages,
            "pagina_actual": page,
            "por_pagina": per_page
        }
