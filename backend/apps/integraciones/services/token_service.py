import json
import secrets
from datetime import timedelta
from urllib import error, parse, request

from django.db import transaction
from django.utils import timezone

from apps.integraciones.models import ApiToken

from . import credential_service


TOKEN_LIFETIME_MINUTES = 55
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
TOKEN_SAFETY_MARGIN_SECONDS = 60


def validar_expiracion(token: ApiToken) -> bool:
    if not token or not token.fecha_expiracion:
        return False
    return token.fecha_expiracion > timezone.now()


def _is_graph_credential(credencial) -> bool:
    servicio = getattr(credencial, "api_servicio", None)
    if servicio is None:
        servicio = credencial.api_servicio
    service_name = (servicio.nombre_servicio or "").casefold()
    provider_name = (servicio.proveedor or "").casefold()
    return "microsoft graph" in service_name or provider_name == "microsoft"


def _request_graph_token(credencial):
    tenant_id = credential_service.get_tenant_id_plain(credencial)
    client_id = credential_service.get_client_id_plain(credencial)
    client_secret = credential_service.decrypt_secret(
        credencial.secret_encriptado,
        credencial.iv_secret,
    )
    if not tenant_id or not client_id or not client_secret:
        raise ValueError(
            "La credencial de Microsoft Graph no tiene tenant_id, client_id o secret validos."
        )

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    form_data = parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": GRAPH_SCOPE,
            "grant_type": "client_credentials",
        }
    ).encode("utf-8")
    req = request.Request(
        token_url,
        data=form_data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise ValueError(f"No fue posible obtener token Graph: {details}") from exc
    except error.URLError as exc:
        raise ValueError(
            f"No fue posible conectar con Microsoft Graph para obtener el token: {exc.reason}"
        ) from exc

    access_token = payload.get("access_token")
    if not access_token:
        raise ValueError("Microsoft Graph no devolvio `access_token`.")

    expires_in = int(payload.get("expires_in") or 3600)
    safe_expires_in = max(expires_in - TOKEN_SAFETY_MARGIN_SECONDS, 60)
    fecha_expiracion = timezone.now() + timedelta(seconds=safe_expires_in)
    return access_token, payload.get("refresh_token"), fecha_expiracion


def _build_mock_tokens(credencial) -> tuple[str, str]:
    access_token = f"mock-access-{credencial.id_api_credencial}-{secrets.token_urlsafe(32)}"
    refresh_token = f"mock-refresh-{credencial.id_api_credencial}-{secrets.token_urlsafe(48)}"
    return access_token, refresh_token


def _persist_token(credencial, access_token: str, refresh_token: str | None, fecha_expiracion):
    access_encrypted, iv_access, key_reference = credential_service.encrypt_token_value(access_token)
    refresh_encrypted = None
    iv_refresh = None
    if refresh_token:
        refresh_encrypted, iv_refresh, _ = credential_service.encrypt_token_value(refresh_token)

    now = timezone.now()
    ApiToken.objects.filter(api_credencial=credencial, activo=True).update(activo=False)
    return ApiToken.objects.create(
        api_credencial=credencial,
        access_token_encriptado=access_encrypted,
        iv_access_token=iv_access,
        refresh_token_encriptado=refresh_encrypted,
        iv_refresh_token=iv_refresh,
        fecha_generacion=now,
        fecha_expiracion=fecha_expiracion,
        activo=True,
        referencia_clave_cifrado=key_reference,
    )


@transaction.atomic
def generar_token(credencial):
    if _is_graph_credential(credencial):
        access_token, refresh_token, fecha_expiracion = _request_graph_token(credencial)
    else:
        access_token, refresh_token = _build_mock_tokens(credencial)
        fecha_expiracion = timezone.now() + timedelta(minutes=TOKEN_LIFETIME_MINUTES)
    token = _persist_token(credencial, access_token, refresh_token, fecha_expiracion)
    credencial.ultimo_uso = timezone.now()
    credencial.save(update_fields=["ultimo_uso"])
    return token


@transaction.atomic
def renovar_token(token: ApiToken):
    token.activo = False
    token.save(update_fields=["activo"])
    return generar_token(token.api_credencial)


def _is_mock_token(token: ApiToken) -> bool:
    try:
        return get_access_token_plain(token).startswith("mock-access-")
    except Exception:
        return True


def get_valid_token(credencial):
    token = (
        ApiToken.objects.filter(api_credencial=credencial, activo=True)
        .order_by("-fecha_generacion")
        .first()
    )
    if token and validar_expiracion(token):
        if _is_graph_credential(credencial) and _is_mock_token(token):
            return renovar_token(token)
        return token
    if token:
        return renovar_token(token)
    return generar_token(credencial)


def get_access_token_plain(token: ApiToken) -> str:
    return credential_service.decrypt_token_value(
        token.access_token_encriptado,
        token.iv_access_token,
    )


def get_refresh_token_plain(token: ApiToken) -> str:
    return credential_service.decrypt_token_value(
        token.refresh_token_encriptado,
        token.iv_refresh_token,
    )
