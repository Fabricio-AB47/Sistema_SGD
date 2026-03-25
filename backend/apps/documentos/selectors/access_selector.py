from apps.documentos.models import Documento


def get_documento_for_access(documento_id: int):
    return (
        Documento.objects.select_related("clasificacion", "subido_por")
        .filter(pk=documento_id, activo=True)
        .first()
    )

