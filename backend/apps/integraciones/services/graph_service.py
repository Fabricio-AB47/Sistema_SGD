import json
import os
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib import error, parse, request

from django.conf import settings
from django.core.cache import cache

from apps.integraciones.models import ApiCredencial
from apps.integraciones.services import api_log_service, credential_service, token_service


GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_CACHE_TIMEOUT_SECONDS = 300


class GraphServiceError(Exception):
    pass


@dataclass
class GraphConnectionSummary:
    enabled: bool
    source: str | None
    app_name: str | None
    credential_id: int | None
    tenant_id_masked: str | None
    client_id_masked: str | None
    drive_id: str | None
    drive_user: str | None
    message: str | None = None
    root_item_name: str | None = None
    root_item_id: str | None = None
    root_web_url: str | None = None


def _cache_key(kind: str, value: str) -> str:
    drive_id = getattr(settings, "GRAPH_DRIVE_ID", "").strip() or "default"
    return f"sig:graph:{drive_id}:{kind}:{value}"


def _normalized_graph_path(relative_path: str | PurePosixPath) -> str:
    return "/".join(
        part.casefold()
        for part in str(relative_path).replace("\\", "/").split("/")
        if part
    )


def _mask_value(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _configured_drive_id() -> str:
    drive_id = getattr(settings, "GRAPH_DRIVE_ID", "").strip()
    if not drive_id:
        raise GraphServiceError("No existe `GRAPH_DRIVE_ID` configurado.")
    return drive_id


def _find_graph_credential() -> ApiCredencial | None:
    return (
        ApiCredencial.objects.select_related("api_servicio")
        .filter(
            activo=True,
            api_servicio__activo=True,
            api_servicio__nombre_servicio__iexact="Microsoft Graph",
        )
        .order_by("-fecha_creacion", "-id_api_credencial")
        .first()
    )


def _env_graph_credential() -> dict[str, Any] | None:
    tenant_id = os.getenv("MS_TENANT_ID", "").strip()
    client_id = os.getenv("MS_CLIENT_ID", "").strip()
    client_secret = os.getenv("MS_CLIENT_SECRET", "").strip()
    if not (tenant_id and client_id and client_secret):
        return None
    return {
        "source": "env",
        "app_name": "Microsoft Graph (env)",
        "credential_id": None,
        "tenant_id": tenant_id,
        "client_id": client_id,
        "client_secret": client_secret,
        "credential": None,
        "api_servicio": None,
    }


def is_graph_configured() -> bool:
    if not getattr(settings, "GRAPH_DRIVE_ID", "").strip():
        return False
    return _find_graph_credential() is not None or _env_graph_credential() is not None


def require_graph_configuration() -> None:
    if not is_graph_configured():
        raise GraphServiceError(
            "Microsoft Graph no esta configurado. Define GRAPH_DRIVE_ID y una credencial activa o las variables MS_*."
        )


def get_graph_credential_payload() -> dict[str, Any]:
    credencial = _find_graph_credential()
    if credencial:
        return {
            "source": "api_credencial",
            "app_name": credencial.nombre_aplicacion,
            "credential_id": credencial.pk,
            "tenant_id": credencial.tenant_id_plain,
            "client_id": credencial.client_id_plain,
            "client_secret": credential_service.decrypt_secret(
                credencial.secret_encriptado,
                credencial.iv_secret,
            ),
            "credential": credencial,
            "api_servicio": credencial.api_servicio,
        }

    env_payload = _env_graph_credential()
    if env_payload:
        return env_payload

    raise GraphServiceError(
        "No existe una credencial activa de Microsoft Graph en `api_credencial` ni variables MS_* en entorno."
    )


def _quote_graph_path(relative_path: str | PurePosixPath) -> str:
    normalized = PurePosixPath(str(relative_path).replace("\\", "/"))
    return "/".join(parse.quote(part, safe="") for part in normalized.parts if part)


def _log_graph_call(payload: dict[str, Any], *, api_path: str, method: str, result: str, detail=None):
    api_servicio = payload.get("api_servicio")
    if api_servicio is None:
        return
    api_log_service.registrar_consumo_api(
        api_servicio=api_servicio,
        endpoint=api_path,
        metodo_http=method,
        resultado=result,
        detalle=detail,
    )


def _graph_json_request(
    method: str,
    api_path: str,
    *,
    access_token: str,
    payload: dict[str, Any] | None = None,
    expected_status: tuple[int, ...] = (200,),
    log_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{GRAPH_API_BASE}{api_path}"
    data = None
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8") or "{}"
            if response.status not in expected_status:
                raise GraphServiceError(
                    f"Respuesta inesperada de Graph ({response.status}) para {api_path}."
                )
            parsed = json.loads(body)
            if log_payload is not None:
                _log_graph_call(log_payload, api_path=api_path, method=method, result=str(response.status))
            return parsed
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        if log_payload is not None:
            _log_graph_call(log_payload, api_path=api_path, method=method, result=str(exc.code), detail=details)
        raise GraphServiceError(
            f"Graph devolvio {exc.code} en {api_path}. {details}"
        ) from exc
    except error.URLError as exc:
        if log_payload is not None:
            _log_graph_call(log_payload, api_path=api_path, method=method, result="ERROR", detail=str(exc.reason))
        raise GraphServiceError(f"No fue posible conectar con Microsoft Graph: {exc.reason}") from exc


def _graph_binary_request(
    method: str,
    api_path: str,
    *,
    access_token: str,
    body: bytes,
    content_type: str | None = None,
    expected_status: tuple[int, ...] = (200, 201),
    log_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{GRAPH_API_BASE}{api_path}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": content_type or "application/octet-stream",
    }
    req = request.Request(url, data=body, method=method.upper(), headers=headers)
    try:
        with request.urlopen(req, timeout=60) as response:
            raw_body = response.read().decode("utf-8") or "{}"
            if response.status not in expected_status:
                raise GraphServiceError(
                    f"Respuesta inesperada de Graph ({response.status}) para {api_path}."
                )
            parsed = json.loads(raw_body)
            if log_payload is not None:
                _log_graph_call(log_payload, api_path=api_path, method=method, result=str(response.status))
            return parsed
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        if log_payload is not None:
            _log_graph_call(log_payload, api_path=api_path, method=method, result=str(exc.code), detail=details)
        raise GraphServiceError(
            f"Graph devolvio {exc.code} en {api_path}. {details}"
        ) from exc
    except error.URLError as exc:
        if log_payload is not None:
            _log_graph_call(log_payload, api_path=api_path, method=method, result="ERROR", detail=str(exc.reason))
        raise GraphServiceError(f"No fue posible conectar con Microsoft Graph: {exc.reason}") from exc


def _graph_content_request(
    method: str,
    api_path: str,
    *,
    access_token: str,
    expected_status: tuple[int, ...] = (200,),
    log_payload: dict[str, Any] | None = None,
) -> tuple[bytes, dict[str, str]]:
    url = f"{GRAPH_API_BASE}{api_path}"
    headers = {"Authorization": f"Bearer {access_token}"}
    req = request.Request(url, method=method.upper(), headers=headers)
    try:
        with request.urlopen(req, timeout=60) as response:
            if response.status not in expected_status:
                raise GraphServiceError(
                    f"Respuesta inesperada de Graph ({response.status}) para {api_path}."
                )
            if log_payload is not None:
                _log_graph_call(log_payload, api_path=api_path, method=method, result=str(response.status))
            return response.read(), dict(response.info())
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        if log_payload is not None:
            _log_graph_call(log_payload, api_path=api_path, method=method, result=str(exc.code), detail=details)
        raise GraphServiceError(
            f"Graph devolvio {exc.code} en {api_path}. {details}"
        ) from exc
    except error.URLError as exc:
        if log_payload is not None:
            _log_graph_call(log_payload, api_path=api_path, method=method, result="ERROR", detail=str(exc.reason))
        raise GraphServiceError(f"No fue posible conectar con Microsoft Graph: {exc.reason}") from exc


def get_graph_access_token(payload: dict[str, Any] | None = None) -> str:
    payload = payload or get_graph_credential_payload()
    credencial = payload.get("credential")
    if credencial is not None:
        token = token_service.get_valid_token(credencial)
        return token_service.get_access_token_plain(token)

    return _request_env_token(payload)


def get_graph_session() -> tuple[dict[str, Any], str]:
    require_graph_configuration()
    payload = get_graph_credential_payload()
    access_token = get_graph_access_token(payload)
    return payload, access_token


def _request_env_token(payload: dict[str, Any]) -> str:
    form_data = parse.urlencode(
        {
            "client_id": payload["client_id"],
            "client_secret": payload["client_secret"],
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
    ).encode("utf-8")
    token_url = (
        f"https://login.microsoftonline.com/{payload['tenant_id']}/oauth2/v2.0/token"
    )
    req = request.Request(
        token_url,
        data=form_data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
            access_token = body.get("access_token")
            if not access_token:
                raise GraphServiceError("Microsoft Graph no devolvio `access_token`.")
            return access_token
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise GraphServiceError(f"No fue posible obtener token Graph: {details}") from exc


def get_drive_root_item(
    *,
    payload: dict[str, Any] | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    cached_root_item = cache.get(_cache_key("root-item", "root"))
    if cached_root_item is not None:
        return cached_root_item

    payload = payload or get_graph_credential_payload()
    access_token = access_token or get_graph_access_token(payload)
    drive_id = parse.quote(_configured_drive_id(), safe="")
    root_item = _graph_json_request(
        "GET",
        f"/drives/{drive_id}/root?$select=id,name,webUrl,parentReference",
        access_token=access_token,
        log_payload=payload,
    )
    cache.set(_cache_key("root-item", "root"), root_item, GRAPH_CACHE_TIMEOUT_SECONDS)
    return root_item


def get_connection_summary(*, validate: bool = False) -> GraphConnectionSummary:
    try:
        payload = get_graph_credential_payload()
        summary = GraphConnectionSummary(
            enabled=True,
            source=payload["source"],
            app_name=payload["app_name"],
            credential_id=payload.get("credential_id"),
            tenant_id_masked=_mask_value(payload["tenant_id"]),
            client_id_masked=_mask_value(payload["client_id"]),
            drive_id=_configured_drive_id(),
            drive_user=getattr(settings, "GRAPH_DRIVE_USER", "").strip() or None,
            message="Configuracion lista.",
        )
        if validate:
            root_item = get_drive_root_item()
            summary.root_item_name = root_item.get("name")
            summary.root_item_id = root_item.get("id")
            summary.root_web_url = root_item.get("webUrl")
            summary.message = "Conexion Graph validada correctamente."
        return summary
    except GraphServiceError as exc:
        return GraphConnectionSummary(
            enabled=False,
            source=None,
            app_name=None,
            credential_id=None,
            tenant_id_masked=None,
            client_id_masked=None,
            drive_id=getattr(settings, "GRAPH_DRIVE_ID", "").strip() or None,
            drive_user=getattr(settings, "GRAPH_DRIVE_USER", "").strip() or None,
            message=str(exc),
        )


def _list_children(
    *,
    parent_item_id: str,
    access_token: str,
    log_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    drive_id = parse.quote(_configured_drive_id(), safe="")
    data = _graph_json_request(
        "GET",
        f"/drives/{drive_id}/items/{parse.quote(parent_item_id, safe='')}/children?$select=id,name,folder,webUrl,parentReference",
        access_token=access_token,
        log_payload=log_payload,
    )
    return data.get("value", [])


def _create_child_folder(
    *,
    parent_item_id: str,
    folder_name: str,
    access_token: str,
    log_payload: dict[str, Any],
) -> dict[str, Any]:
    drive_id = parse.quote(_configured_drive_id(), safe="")
    return _graph_json_request(
        "POST",
        f"/drives/{drive_id}/items/{parse.quote(parent_item_id, safe='')}/children",
        access_token=access_token,
        payload={
            "name": folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "replace",
        },
        expected_status=(200, 201),
        log_payload=log_payload,
    )


def _normalize_graph_path_parts(relative_path: str | PurePosixPath) -> list[str]:
    path_parts = [
        part
        for part in str(relative_path).replace("\\", "/").split("/")
        if part
    ]
    if not path_parts:
        raise GraphServiceError("La ruta de carpeta Graph no puede estar vacia.")
    return path_parts


def _ensure_drive_folder(
    *,
    relative_path: str | PurePosixPath,
    payload: dict[str, Any],
    access_token: str,
) -> dict[str, Any]:
    path_parts = _normalize_graph_path_parts(relative_path)
    current_item = get_drive_root_item(payload=payload, access_token=access_token)
    current_path_parts: list[str] = []

    for part in path_parts:
        current_path_parts.append(part)
        current_path = "/".join(current_path_parts)
        cached_item = cache.get(_cache_key("folder-item", _normalized_graph_path(current_path)))
        if cached_item is not None:
            current_item = cached_item
            continue

        children = _list_children(
            parent_item_id=current_item["id"],
            access_token=access_token,
            log_payload=payload,
        )
        next_item = next(
            (
                child
                for child in children
                if child.get("name", "").casefold() == part.casefold()
                and child.get("folder") is not None
            ),
            None,
        )
        if next_item is None:
            next_item = _create_child_folder(
                parent_item_id=current_item["id"],
                folder_name=part,
                access_token=access_token,
                log_payload=payload,
            )
        current_item = next_item
        cache.set(
            _cache_key("folder-item", _normalized_graph_path(current_path)),
            current_item,
            GRAPH_CACHE_TIMEOUT_SECONDS,
        )

    return current_item


def ensure_drive_folder(
    relative_path: str | PurePosixPath,
    *,
    payload: dict[str, Any] | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    if payload is None or access_token is None:
        payload, access_token = get_graph_session()
    return _ensure_drive_folder(
        relative_path=relative_path,
        payload=payload,
        access_token=access_token,
    )


def upload_file(
    *,
    relative_folder_path: str | PurePosixPath,
    file_name: str,
    content: bytes,
    content_type: str | None = None,
    ensure_folder: bool = True,
    payload: dict[str, Any] | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    if not file_name:
        raise GraphServiceError("El nombre del archivo Graph es obligatorio.")

    if payload is None or access_token is None:
        payload, access_token = get_graph_session()
    if ensure_folder:
        _ensure_drive_folder(
            relative_path=relative_folder_path,
            payload=payload,
            access_token=access_token,
        )

    drive_id = parse.quote(_configured_drive_id(), safe="")
    relative_file_path = PurePosixPath(str(relative_folder_path).replace("\\", "/")) / file_name
    api_path = (
        f"/drives/{drive_id}/root:/{_quote_graph_path(relative_file_path)}:/content"
    )
    return _graph_binary_request(
        "PUT",
        api_path,
        access_token=access_token,
        body=content,
        content_type=content_type,
        expected_status=(200, 201),
        log_payload=payload,
    )


def download_file_by_item_id(item_id: str) -> tuple[bytes, dict[str, str]]:
    if not item_id:
        raise GraphServiceError("El item_id de Graph es obligatorio para descargar el archivo.")

    require_graph_configuration()
    payload = get_graph_credential_payload()
    access_token = get_graph_access_token(payload)
    drive_id = parse.quote(_configured_drive_id(), safe="")
    api_path = f"/drives/{drive_id}/items/{parse.quote(item_id, safe='')}/content"
    return _graph_content_request(
        "GET",
        api_path,
        access_token=access_token,
        expected_status=(200, 302),
        log_payload=payload,
    )
