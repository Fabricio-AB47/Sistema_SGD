from apps.integraciones.models import ApiCredencial, ApiServicio


def obtener_servicios_activos():
    return ApiServicio.objects.filter(activo=True).order_by("nombre_servicio", "proveedor")


def obtener_credenciales_por_servicio(servicio=None):
    queryset = ApiCredencial.objects.select_related("api_servicio").filter(activo=True)
    if servicio is None:
        return queryset.order_by("nombre_aplicacion")
    servicio_id = getattr(servicio, "id_api_servicio", servicio)
    return queryset.filter(api_servicio_id=servicio_id).order_by("nombre_aplicacion")
