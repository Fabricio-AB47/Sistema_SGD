"""
Servicio de gestión de contraseñas.
Forza Argon2 para todos los hashes nuevos y soporta rehash automático.
"""

from dataclasses import dataclass

from django.contrib.auth.hashers import (
    Argon2PasswordHasher,
    check_password,
    identify_hasher,
    make_password,
)


# Hasher principal (argon2) instanciado una vez.
_argon2 = Argon2PasswordHasher()


@dataclass
class PasswordCheckResult:
    """
    Resultado de verificación de contraseña.
    - valid: la contraseña coincide con el hash almacenado.
    - needs_rehash: el hash debe migrarse a Argon2 inmediatamente.
    """
    valid: bool
    needs_rehash: bool


def hash_password(raw_password: str) -> str:
    """
    Genera un hash Argon2 para la contraseña proporcionada.
    Argon2 es obligatorio y único algoritmo permitido para nuevos hashes.
    """
    return make_password(raw_password, hasher=_argon2.algorithm)


def verify_password(raw_password: str, stored_hash: str) -> PasswordCheckResult:
    """
    Verifica la contraseña contra el hash almacenado y determina si requiere migración a Argon2.
    Regla: Argon2 es obligatorio; cualquier hash no Argon2, si es válido, debe rehasearse.
    """
    try:
        hasher = identify_hasher(stored_hash)
    except Exception:
        # Caso legacy: si el valor almacenado está en texto plano, migrarlo al primer login.
        if stored_hash == raw_password:
            return PasswordCheckResult(valid=True, needs_rehash=True)
        return PasswordCheckResult(valid=False, needs_rehash=False)

    # check_password con preferred=_argon2 permite validar legacy y recomendar Argon2.
    valid = check_password(raw_password, stored_hash, preferred=_argon2)
    if not valid:
        return PasswordCheckResult(valid=False, needs_rehash=False)

    # Necesita rehash si no es Argon2 o si Argon2 indica actualización.
    needs_rehash = (
        hasher.algorithm != _argon2.algorithm or hasher.must_update(stored_hash)
    )
    return PasswordCheckResult(valid=True, needs_rehash=needs_rehash)


def needs_rehash(stored_hash: str) -> bool:
    """
    Indica si el hash almacenado debería migrarse a Argon2.
    """
    try:
        hasher = identify_hasher(stored_hash)
    except Exception:
        return True
    return hasher.algorithm != _argon2.algorithm or hasher.must_update(stored_hash)
