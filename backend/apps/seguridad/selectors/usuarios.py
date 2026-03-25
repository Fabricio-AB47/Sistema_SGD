from django.db import transaction

from apps.usuarios.models import Usuario
from apps.seguridad.models import UsuarioCredencial


def get_usuario_activo_por_correo(correo: str):
    return Usuario.objects.filter(correo__iexact=correo, activo=True).first()


@transaction.atomic
def get_credencial_con_lock(usuario_id: int):
    return (
        UsuarioCredencial.objects.select_for_update()
        .filter(usuario_id=usuario_id)
        .first()
    )
