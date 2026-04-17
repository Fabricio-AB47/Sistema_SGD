from __future__ import annotations

from apps.usuarios.selectors import get_usuario_area_cargo_for_context, get_usuario_area_cargo_options


def resolve_structural_session_context(*, usuario_id: int, assignment_id: int | None = None) -> dict:
    assignment = get_usuario_area_cargo_for_context(usuario=usuario_id, assignment_id=assignment_id)
    if assignment is None:
        return {
            "active_assignment_id": None,
            "active_area_id": None,
            "active_area_name": None,
            "active_cargo_id": None,
            "active_cargo_name": None,
            "operational_roles": (),
            "available_assignments": (),
        }

    area_name = (assignment.area.nombre_area or "").strip()
    cargo_name = (assignment.cargo.nombre_cargo or "").strip()

    options = tuple(
        {
            "id": option.pk,
            "area": option.area.nombre_area,
            "cargo": option.cargo.nombre_cargo,
        }
        for option in get_usuario_area_cargo_options(usuario_id)
    )

    return {
        "active_assignment_id": assignment.pk,
        "active_area_id": assignment.area_id,
        "active_area_name": area_name,
        "active_cargo_id": assignment.cargo_id,
        "active_cargo_name": cargo_name,
        "operational_roles": tuple(role for role in (area_name.upper(), cargo_name.upper()) if role),
        "available_assignments": options,
    }


def hydrate_request_session_context(request, *, usuario_id: int, assignment_id: int | None = None) -> dict:
    context = resolve_structural_session_context(usuario_id=usuario_id, assignment_id=assignment_id)
    request.session["sig_active_assignment_id"] = context["active_assignment_id"]
    request.session["sig_active_area_id"] = context["active_area_id"]
    request.session["sig_active_area_name"] = context["active_area_name"]
    request.session["sig_active_cargo_id"] = context["active_cargo_id"]
    request.session["sig_active_cargo_name"] = context["active_cargo_name"]
    request.session["sig_operational_roles"] = list(context["operational_roles"])
    request.session["sig_assignment_options"] = list(context["available_assignments"])
    return context
