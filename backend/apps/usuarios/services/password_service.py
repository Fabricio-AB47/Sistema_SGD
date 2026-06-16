from __future__ import annotations

import secrets
from dataclasses import dataclass

from django.contrib.auth.hashers import (
    Argon2PasswordHasher,
    check_password,
    identify_hasher,
    make_password,
)
from django.db import transaction
from django.utils import timezone

from apps.auditoria.services.auditoria_service import registrar_evento
from apps.usuarios.models import HistorialPassword, UsuarioCredencial


ARGON2_ALGORITHM = "argon2"
_argon2 = Argon2PasswordHasher()


@dataclass(frozen=True)
class PasswordCheckResult:
    valid: bool
    needs_rehash: bool
    algorithm: str | None = None


@dataclass(frozen=True)
class PasswordUpgradeResult:
    upgraded: bool
    normalized_algorithm: bool = False


def hash_password_argon2(raw_password: str) -> str:
    if not raw_password:
        raise ValueError("La contrasena no puede ser vacia.")
    return make_password(raw_password, hasher=ARGON2_ALGORITHM)


def hash_password(raw_password: str) -> str:
    return hash_password_argon2(raw_password)


def verify_password(raw_password: str, stored_hash: str) -> PasswordCheckResult:
    if raw_password is None or not stored_hash:
        return PasswordCheckResult(valid=False, needs_rehash=False, algorithm=None)

    try:
        hasher = identify_hasher(stored_hash)
    except Exception:
        valid = secrets.compare_digest(str(raw_password), str(stored_hash))
        return PasswordCheckResult(valid=valid, needs_rehash=valid, algorithm=None)

    valid = check_password(raw_password, stored_hash)
    if not valid:
        return PasswordCheckResult(valid=False, needs_rehash=False, algorithm=hasher.algorithm)

    needs_rehash = hasher.algorithm != ARGON2_ALGORITHM or _argon2.must_update(stored_hash)
    return PasswordCheckResult(valid=True, needs_rehash=needs_rehash, algorithm=hasher.algorithm)


@transaction.atomic
def upgrade_password_if_needed(
    credencial: UsuarioCredencial,
    raw_password: str,
    *,
    check: PasswordCheckResult | None = None,
    actor=None,
    request=None,
    force: bool = False,
) -> PasswordUpgradeResult:
    if check is None:
        check = verify_password(raw_password, credencial.password_hash)
    if not check.valid:
        return PasswordUpgradeResult(upgraded=False, normalized_algorithm=False)

    now = timezone.now()
    current_algorithm = (credencial.algoritmo_hash or "").strip().lower()
    should_rehash = force or check.needs_rehash

    if should_rehash:
        previous_hash = credencial.password_hash
        previous_algorithm = credencial.algoritmo_hash
        HistorialPassword.objects.create(
            usuario=credencial.usuario,
            password_hash=previous_hash,
            algoritmo_hash=previous_algorithm or ARGON2_ALGORITHM,
            fecha_cambio=now,
        )
        credencial.password_hash = hash_password_argon2(raw_password)
        credencial.algoritmo_hash = ARGON2_ALGORITHM
        credencial.password_version = (credencial.password_version or 0) + 1
        credencial.fecha_cambio = now
        credencial.save(
            update_fields=[
                "password_hash",
                "algoritmo_hash",
                "password_version",
                "fecha_cambio",
            ]
        )
        registrar_evento(
            accion="REHASH_PASSWORD",
            descripcion=f"Se actualizo el hash de password del usuario {credencial.usuario} a Argon2.",
            usuario=actor or credencial.usuario,
            tipo_evento="SEGURIDAD",
            tabla_afectada="usuario_credencial",
            id_registro=credencial.usuario_id,
            valores_anteriores={"algoritmo_hash": previous_algorithm},
            valores_nuevos={
                "algoritmo_hash": ARGON2_ALGORITHM,
                "password_version": credencial.password_version,
            },
            criticidad="MEDIA",
            request=request,
        )
        return PasswordUpgradeResult(upgraded=True, normalized_algorithm=False)

    if current_algorithm != ARGON2_ALGORITHM:
        credencial.algoritmo_hash = ARGON2_ALGORITHM
        credencial.save(update_fields=["algoritmo_hash"])
        return PasswordUpgradeResult(upgraded=False, normalized_algorithm=True)

    return PasswordUpgradeResult(upgraded=False, normalized_algorithm=False)
