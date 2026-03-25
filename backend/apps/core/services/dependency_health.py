from __future__ import annotations

from django.db import connection
from django.db.utils import DatabaseError


class DependencyValidationError(Exception):
    pass


def ensure_database_connection() -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError as exc:
        raise DependencyValidationError(
            "No fue posible validar la conexion con SQL Server."
        ) from exc
