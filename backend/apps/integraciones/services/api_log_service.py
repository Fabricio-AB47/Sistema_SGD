import json

from django.utils import timezone

from apps.integraciones.models import ApiConsumoLog


def _stringify_detail(detalle) -> str:
    if detalle is None:
        return ""
    if isinstance(detalle, str):
        return detalle[:1000]
    try:
        return json.dumps(detalle, ensure_ascii=False, default=str)[:1000]
    except TypeError:
        return str(detalle)[:1000]


def registrar_consumo_api(
    api_servicio,
    endpoint: str,
    metodo_http: str,
    usuario=None,
    ip: str | None = None,
    resultado: str | None = None,
    detalle=None,
):
    return ApiConsumoLog.objects.create(
        api_servicio=api_servicio,
        endpoint=endpoint,
        metodo_http=metodo_http.upper(),
        usuario_sistema=usuario,
        fecha_consumo=timezone.now(),
        ip=ip,
        resultado=(resultado or "")[:50],
        detalle=_stringify_detail(detalle),
    )
