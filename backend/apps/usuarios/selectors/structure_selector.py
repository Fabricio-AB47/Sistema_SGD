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


def _resolve_usuario_id(usuario) -> int | None:
    return getattr(usuario, "pk", None) or getattr(usuario, "id_user", None) or usuario


def get_usuario_area_cargo_options(usuario):
    usuario_id = _resolve_usuario_id(usuario)
    if not usuario_id:
        return UsuarioAreaCargo.objects.none()
    return (
        UsuarioAreaCargo.objects.select_related("area", "cargo")
        .filter(usuario_id=usuario_id, activo=True, area__activo=True, cargo__activo=True)
        .order_by("cargo__nivel_jerarquico", "area__nombre_area", "cargo__nombre_cargo", "-fecha_asignacion")
    )


def get_primary_usuario_area_cargo(usuario):
    return get_usuario_area_cargo_options(usuario).first()


def get_usuario_area_cargo_for_context(*, usuario, assignment_id=None):
    queryset = get_usuario_area_cargo_options(usuario)
    if assignment_id:
        assignment = queryset.filter(pk=assignment_id).first()
        if assignment is not None:
            return assignment
    return queryset.first()


def get_organigrama_institucional():
    assignments = (
        UsuarioAreaCargo.objects.select_related("usuario", "area", "cargo")
        .filter(activo=True)
        .order_by(
            "area__nombre_area",
            "cargo__nivel_jerarquico",
            "cargo__nombre_cargo",
            "usuario__primer_apellido",
            "usuario__primer_nombre",
        )
    )

    assignments_map = {}
    for assignment in assignments:
        cargo_bucket = assignments_map.setdefault(assignment.cargo_id, [])
        cargo_bucket.append(assignment.usuario)

    ordered_areas = []
    for area in AreaInstitucional.objects.filter(activo=True).order_by("nombre_area"):
        cargos = []
        for cargo in (
            CargoArea.objects.filter(area=area, activo=True)
            .order_by("nivel_jerarquico", "nombre_cargo")
        ):
            usuarios = assignments_map.get(cargo.pk, [])
            cargos.append(
                {
                    "cargo": cargo,
                    "usuarios": usuarios,
                }
            )

        ordered_areas.append(
            {
                "area": area,
                "cargos": cargos,
                "usuarios_total": sum(len(item["usuarios"]) for item in cargos),
            }
        )

    return ordered_areas
