"""
Construccion de rutas documentales para la jerarquia CACES.

La provision de carpetas se realiza exclusivamente en Microsoft Graph.
Las funciones locales se conservan solo para compatibilidad de lectura con
registros legacy y no deben crear directorios en disco.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlparse

from django.conf import settings


def get_project_storage_root() -> Path:
    # BASE_DIR apunta a `backend/`; su padre es la raiz del proyecto cargado por el usuario.
    return Path(settings.BASE_DIR).parent


def _normalize_relative_path(value: str | None) -> str:
    return "/".join(
        segment.strip()
        for segment in str(value or "").replace("\\", "/").split("/")
        if segment.strip()
    )


def get_drive_root_path() -> PurePosixPath:
    configured = _normalize_relative_path(getattr(settings, "DOC_PATH_DRIVE", ""))
    if not configured:
        return PurePosixPath(get_project_storage_root().name)
    return PurePosixPath(configured)


def _local_path_from_drive_path(relative_path: PurePosixPath) -> Path:
    project_root = get_project_storage_root()
    drive_root = get_drive_root_path()
    drive_root_parts = tuple(part.casefold() for part in drive_root.parts)
    project_tail = tuple(part.casefold() for part in project_root.parts[-len(drive_root.parts) :])

    if drive_root_parts and project_tail == drive_root_parts:
        local_root = project_root
    else:
        local_root = project_root.joinpath(*drive_root.parts)

    try:
        relative_suffix = relative_path.relative_to(drive_root)
    except ValueError:
        relative_suffix = relative_path

    return local_root.joinpath(*relative_suffix.parts)


def get_local_storage_root() -> Path:
    return _local_path_from_drive_path(get_drive_root_path())


def _slugify_segment(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_")
    return (cleaned or "sin_nombre").upper()


def _named_segment(code: str, name: str) -> str:
    return f"{str(code or '').upper()}_{_slugify_segment(name)}"


def _ciclo_segment_from_values(nombre: str, anio: int | None = None, pk: int | None = None) -> str:
    cycle_code = str(anio or pk or "ciclo")
    return _named_segment(cycle_code, nombre)


def _ciclo_segment(ciclo) -> str:
    return _ciclo_segment_from_values(ciclo.nombre, getattr(ciclo, "anio", None), getattr(ciclo, "pk", None))


def _extract_drive_path_from_sharepoint_url(url: str | None) -> PurePosixPath | None:
    if not url:
        return None

    parsed = urlparse(url)
    query_values = parse_qs(parsed.query)
    raw_path = query_values.get("id", [parsed.path])[0]
    decoded_path = unquote(raw_path)
    marker = "/Documents/"
    if marker not in decoded_path:
        return None

    relative = _normalize_relative_path(decoded_path.split(marker, 1)[1])
    return PurePosixPath(relative) if relative else None


def get_ciclo_auth_drive_root() -> PurePosixPath:
    from_url = _extract_drive_path_from_sharepoint_url(
        getattr(settings, "GRAPH_CICLO_AUTH_FOLDER_URL", "")
    )
    if from_url:
        return from_url

    configured = _normalize_relative_path(getattr(settings, "GRAPH_CICLO_AUTH_FOLDER", ""))
    if configured:
        configured_path = PurePosixPath(configured)
        drive_root = get_drive_root_path()
        if configured_path.parts[: len(drive_root.parts)] == drive_root.parts:
            return configured_path
        return drive_root / configured_path

    return get_drive_root_path() / "DOCUMENTOS_CICLOS_AUTH"


def get_ciclo_auth_local_root() -> Path:
    return _local_path_from_drive_path(get_ciclo_auth_drive_root())


def build_criterio_drive_path(criterio) -> PurePosixPath:
    return get_drive_root_path() / "CRITERIO" / _named_segment(
        criterio.codigo_criterio,
        criterio.nombre_criterio,
    )


def build_criterio_path(criterio) -> Path:
    return _local_path_from_drive_path(build_criterio_drive_path(criterio))


def build_subcriterio_drive_path(subcriterio) -> PurePosixPath:
    return build_criterio_drive_path(subcriterio.criterio) / "SUBCRITERIO" / _named_segment(
        subcriterio.codigo_subcriterio,
        subcriterio.nombre_subcriterio,
    )


def build_subcriterio_path(subcriterio) -> Path:
    return _local_path_from_drive_path(build_subcriterio_drive_path(subcriterio))


def build_indicador_drive_path(indicador) -> PurePosixPath:
    return build_subcriterio_drive_path(indicador.subcriterio) / "INDICADOR" / _named_segment(
        indicador.codigo_indicador,
        indicador.nombre_indicador,
    )


def build_indicador_path(indicador) -> Path:
    return _local_path_from_drive_path(build_indicador_drive_path(indicador))


def build_elemento_drive_path(indicador, elemento) -> PurePosixPath:
    return build_indicador_drive_path(indicador) / "ELEMENTO" / _named_segment(
        elemento.codigo_elemento,
        elemento.nombre_elemento,
    )


def build_elemento_path(indicador, elemento) -> Path:
    return _local_path_from_drive_path(build_elemento_drive_path(indicador, elemento))


def build_document_drive_path(indicador, elemento, ciclo) -> PurePosixPath:
    return build_elemento_drive_path(indicador, elemento) / "CICLO" / _ciclo_segment(ciclo)


def build_document_path(indicador, elemento, ciclo) -> Path:
    return _local_path_from_drive_path(build_document_drive_path(indicador, elemento, ciclo))


def build_ciclo_auth_drive_path(ciclo) -> PurePosixPath:
    return get_ciclo_auth_drive_root() / _ciclo_segment(ciclo)


def build_ciclo_auth_path(ciclo) -> Path:
    return _local_path_from_drive_path(build_ciclo_auth_drive_path(ciclo))


def build_ciclo_auth_drive_path_for_values(nombre: str, anio: int | None = None) -> PurePosixPath:
    return get_ciclo_auth_drive_root() / _ciclo_segment_from_values(nombre, anio)


def build_ciclo_auth_path_for_values(nombre: str, anio: int | None = None) -> Path:
    return _local_path_from_drive_path(build_ciclo_auth_drive_path_for_values(nombre, anio))


def ensure_criterio_path(criterio) -> Path:
    return build_criterio_path(criterio)


def ensure_subcriterio_path(subcriterio) -> Path:
    return build_subcriterio_path(subcriterio)


def ensure_indicador_path(indicador) -> Path:
    return build_indicador_path(indicador)


def ensure_elemento_path(indicador, elemento) -> Path:
    return build_elemento_path(indicador, elemento)


def ensure_document_path(indicador, elemento, ciclo) -> Path:
    return build_document_path(indicador, elemento, ciclo)


def ensure_ciclo_auth_path(ciclo) -> Path:
    return build_ciclo_auth_path(ciclo)


def ensure_ciclo_auth_path_for_values(nombre: str, anio: int | None = None) -> Path:
    return build_ciclo_auth_path_for_values(nombre, anio)
