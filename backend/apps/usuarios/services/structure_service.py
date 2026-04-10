from django.db import transaction
from django.utils import timezone

from apps.usuarios.models import UsuarioAreaCargo, UsuarioSupervisor


class UserStructureError(Exception):
    pass


@transaction.atomic
def crear_area(*, form):
    return form.save()


@transaction.atomic
def crear_cargo(*, form):
    return form.save()


@transaction.atomic
def asignar_usuario_area_cargo(*, usuario, area, cargo):
    if cargo.area_id != area.id_area:
        raise UserStructureError("El cargo seleccionado no pertenece al area indicada.")

    assignment, created = UsuarioAreaCargo.objects.get_or_create(
        usuario=usuario,
        area=area,
        cargo=cargo,
        activo=True,
        defaults={"fecha_asignacion": timezone.now()},
    )
    if not created and not assignment.activo:
        assignment.activo = True
        assignment.fecha_asignacion = timezone.now()
        assignment.save(update_fields=["activo", "fecha_asignacion"])
    return assignment


@transaction.atomic
def asignar_supervisor_usuario(*, usuario, supervisor):
    if usuario.pk == supervisor.pk:
        raise UserStructureError("El usuario no puede ser su propio supervisor.")

    relation, created = UsuarioSupervisor.objects.get_or_create(
        usuario=usuario,
        supervisor=supervisor,
        activo=True,
        defaults={"fecha_asignacion": timezone.now()},
    )
    if not created and not relation.activo:
        relation.activo = True
        relation.fecha_asignacion = timezone.now()
        relation.save(update_fields=["activo", "fecha_asignacion"])
    return relation
