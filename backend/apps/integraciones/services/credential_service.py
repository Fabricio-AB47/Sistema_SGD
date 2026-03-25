import base64
import hashlib
import os
from typing import Tuple

from django.conf import settings

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


KEY_REFERENCE = "sig-api-aes"
NONCE_SIZE = 12
TEXT_PREFIX = "enc::"


def _get_cipher_key() -> bytes:
    seed = os.getenv("SIG_API_CRYPTO_KEY") or settings.SECRET_KEY
    return hashlib.sha256(seed.encode("utf-8")).digest()


def _encrypt_value(value: str) -> Tuple[bytes, bytes, str]:
    if value is None:
        value = ""
    nonce = os.urandom(NONCE_SIZE)
    cipher = AESGCM(_get_cipher_key())
    encrypted = cipher.encrypt(nonce, value.encode("utf-8"), None)
    return encrypted, nonce, KEY_REFERENCE


def _decrypt_value(encrypted_value: bytes, iv_value: bytes) -> str:
    if not encrypted_value:
        return ""
    if not iv_value:
        raise ValueError("El valor cifrado no tiene IV asociado.")
    cipher = AESGCM(_get_cipher_key())
    plain = cipher.decrypt(bytes(iv_value), bytes(encrypted_value), None)
    return plain.decode("utf-8")


def encrypt_secret(secret: str) -> Tuple[bytes, bytes, str]:
    return _encrypt_value(secret)


def decrypt_secret(secret_encrypted: bytes, iv_secret: bytes) -> str:
    return _decrypt_value(secret_encrypted, iv_secret)


def encrypt_text_value(value: str | None) -> str | None:
    if not value:
        return value
    if value.startswith(TEXT_PREFIX):
        return value
    nonce = os.urandom(NONCE_SIZE)
    cipher = AESGCM(_get_cipher_key())
    encrypted = cipher.encrypt(nonce, value.encode("utf-8"), None)
    payload = base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")
    return f"{TEXT_PREFIX}{payload}"


def decrypt_text_value(value: str | None) -> str:
    if not value:
        return ""
    if not value.startswith(TEXT_PREFIX):
        return value
    raw = base64.urlsafe_b64decode(value[len(TEXT_PREFIX) :].encode("ascii"))
    nonce, encrypted = raw[:NONCE_SIZE], raw[NONCE_SIZE:]
    cipher = AESGCM(_get_cipher_key())
    plain = cipher.decrypt(nonce, encrypted, None)
    return plain.decode("utf-8")


def get_client_id_plain(credencial) -> str:
    return decrypt_text_value(credencial.client_id)


def get_tenant_id_plain(credencial) -> str:
    return decrypt_text_value(credencial.tenant_id)


def encrypt_token_value(token_value: str) -> Tuple[bytes, bytes, str]:
    return _encrypt_value(token_value)


def decrypt_token_value(token_encrypted: bytes, iv_token: bytes) -> str:
    return _decrypt_value(token_encrypted, iv_token)
