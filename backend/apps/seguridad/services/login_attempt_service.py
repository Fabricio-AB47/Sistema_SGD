"""
Servicio centralizado para control de intentos de login y bloqueos.
"""

from datetime import timedelta
from django.utils import timezone


MAX_INTENTOS = 5          # Límite de intentos fallidos antes de bloqueo.
BLOQUEO_MINUTOS = 15      # Duración del bloqueo temporal.


def is_blocked(credencial) -> bool:
    """
    Retorna True si la credencial está bloqueada actualmente.
    """
    if credencial.bloqueado_hasta is None:
        return False
    return credencial.bloqueado_hasta > timezone.now()


def register_failure(credencial):
    """
    Incrementa intentos fallidos y aplica bloqueo temporal si excede el límite.
    """
    now = timezone.now()
    credencial.intentos_fallidos += 1
    credencial.ultimo_intento_fallido = now

    if credencial.intentos_fallidos >= MAX_INTENTOS:
        credencial.bloqueado_hasta = now + timedelta(minutes=BLOQUEO_MINUTOS)

    credencial.save(
        update_fields=["intentos_fallidos", "ultimo_intento_fallido", "bloqueado_hasta"]
    )
    return credencial


def reset_attempts(credencial):
    """
    Reinicia contadores de intentos y bloqueo.
    """
    credencial.intentos_fallidos = 0
    credencial.bloqueado_hasta = None
    credencial.ultimo_intento_fallido = None
    credencial.save(
        update_fields=["intentos_fallidos", "bloqueado_hasta", "ultimo_intento_fallido"]
    )
    return credencial
