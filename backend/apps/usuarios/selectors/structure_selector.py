from apps.usuarios.models import AreaInstitucional, CargoArea, UsuarioAreaCargo, UsuarioSupervisor


def get_areas_queryset():
    return AreaInstitucional.objects.order_by("nombre_area")


def get_cargos_queryset(*, area_id=None):
    queryset = CargoArea.objects.select_related("area").order_by(
        "area__nombre_area",
        "nivel_jerarquico",
        "nombre_cargo",
    )
    if area_id:
        queryset = queryset.filter(area_id=area_id)
    return queryset


def get_usuario_area_cargos(usuario):
    return (
        UsuarioAreaCargo.objects.select_related("area", "cargo")
        .filter(usuario=usuario)
        .order_by("-activo", "area__nombre_area", "cargo__nivel_jerarquico")
    )


def get_usuario_supervisores(usuario):
    return (
        UsuarioSupervisor.objects.select_related("supervisor")
        .filter(usuario=usuario)
        .order_by("-activo", "-fecha_asignacion")
    )
