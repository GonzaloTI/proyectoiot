from flask import session
from modelos.Dusuarios import Dusuarios

# Instancia del modelo Dusuarios para la verificación de credenciales de sesión
d_usuarios = Dusuarios()

def procesar_login(usuario, password):
    """
    Procesa la lógica de negocio para el inicio de sesión:
    1. Limpia y valida la presencia de campos obligatorios.
    2. Valida la longitud máxima de caracteres (40 para usuario y contraseña).
    3. Verifica las credenciales a través del modelo de datos Dusuarios.
    4. Guarda la información relevante del usuario en la sesión de Flask.
    
    Retorna:
        tuple: (exito: bool, mensaje_error: str o None)
    """
    usuario = (usuario or '').strip()
    password = (password or '').strip()
    
    # 1. Validación de campos obligatorios
    if not usuario or not password:
        return False, "Por favor, complete todos los campos."
        
    # 2. Validación de longitud máxima (40 caracteres)
    if len(usuario) > 40:
        return False, "El usuario no debe exceder los 40 caracteres."
        
    if len(password) > 40:
        return False, "La contraseña no debe exceder los 40 caracteres."
        
    # 3. Verificación de credenciales en el Modelo Dusuarios
    user, err_msg = d_usuarios.verificar_credenciales(usuario, password)
    if not user:
        return False, err_msg
        
    # 4. Establecer datos en la sesión
    session['user_id'] = user['id']
    session['usuario'] = user['usuario']
    session['roles'] = user.get('roles', [])
    session['is_admin'] = ('Admin' in user.get('roles', []))
    
    return True, None


def cerrar_sesion():
    """
    Limpia todos los datos de la sesión activa en Flask.
    """
    session.clear()
