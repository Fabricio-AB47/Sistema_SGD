from apps.usuarios.services.auth_service import authenticate_user
from apps.usuarios.services.session_service import close_session


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def autenticar(correo: str, password: str, remember: bool, ip: str, user_agent: str):
    result = authenticate_user(
        correo=correo,
        password=password,
        remember=remember,
        ip=ip or "",
        user_agent=(user_agent or "")[:300],
    )
    if result.status == "success":
        return {
            "token": result.session_token,
            "expira": result.session_expires_at,
            "usuario": result.usuario,
            "session_id": result.session_id,
        }
    if result.status == "blocked":
        raise AuthError("Cuenta bloqueada temporalmente. Intente mas tarde.", status=423)
    if result.status == "requires_otp":
        raise AuthError("Se requiere validacion OTP para completar el acceso.", status=428)
    raise AuthError("Credenciales invalidas", status=401)


def cerrar_sesion(token_plain: str):
    result = close_session(token_plain=token_plain, reason="manual")
    return 1 if result.get("updated") else 0
