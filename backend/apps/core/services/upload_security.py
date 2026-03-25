from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError


def validate_uploaded_file(uploaded_file, *, label: str = "archivo") -> None:
    if uploaded_file is None:
        raise ValidationError(f"Debes seleccionar un {label}.")

    file_size = int(getattr(uploaded_file, "size", 0) or 0)
    if file_size <= 0:
        raise ValidationError(f"El {label} esta vacio.")

    max_bytes = int(getattr(settings, "SIG_MAX_UPLOAD_FILE_BYTES", 25 * 1024 * 1024))
    if file_size > max_bytes:
        max_mb = int(getattr(settings, "SIG_MAX_UPLOAD_FILE_MB", 25))
        raise ValidationError(
            f"El {label} supera el limite permitido de {max_mb} MB."
        )

    file_extension = Path(str(getattr(uploaded_file, "name", "") or "")).suffix.lower()
    allowed_extensions = {
        str(extension).strip().lower()
        for extension in getattr(settings, "SIG_ALLOWED_UPLOAD_EXTENSIONS", ())
        if str(extension).strip()
    }
    if file_extension not in allowed_extensions:
        raise ValidationError(
            f"El formato del {label} no esta permitido."
        )

    declared_content_type = (
        str(getattr(uploaded_file, "content_type", "") or "").split(";", 1)[0].strip().lower()
    )
    allowed_content_types = {
        str(content_type).strip().lower()
        for content_type in getattr(settings, "SIG_ALLOWED_UPLOAD_CONTENT_TYPES", ())
        if str(content_type).strip()
    }
    if declared_content_type and declared_content_type not in allowed_content_types:
        raise ValidationError(
            f"El tipo de contenido del {label} no esta permitido."
        )
