from django import forms
from django.db.models import Q

from apps.core.models import ClasificacionDocumento
from apps.documentos.forms import StructuredDocumentUploadForm
from apps.documentos.selectors import cycle_allows_document_upload


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = " ".join((value or "").strip().split())
    return normalized or None


def _get_institutional_evidence_classification():
    queryset = ClasificacionDocumento.objects.filter(activo=True)
    return (
        queryset.filter(codigo__iexact="EVID").first()
        or queryset.filter(nombre__iexact="Evidencia institucional").first()
        or queryset.filter(
            Q(nombre__icontains="evidencia") & Q(nombre__icontains="institucional")
        ).first()
    )


class MatrixEvidenceRegistrationForm(StructuredDocumentUploadForm):
    comentario = forms.CharField(
        max_length=500,
        required=False,
        label="Comentario del registro",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        allowed_cycle_ids = kwargs.pop("allowed_cycle_ids", None)
        super().__init__(*args, **kwargs)
        if allowed_cycle_ids is not None:
            self.fields["ciclo"].queryset = self.fields["ciclo"].queryset.filter(
                pk__in=list(allowed_cycle_ids)
            )
        if self.fields["ciclo"].initial:
            self.fields["ciclo"].disabled = True
        if self.initial.get("indicador"):
            self.fields["indicador"].disabled = True
        if self.initial.get("elemento_fundamental"):
            self.fields["elemento_fundamental"].disabled = True

        evidencia_clasificacion = _get_institutional_evidence_classification()
        if evidencia_clasificacion:
            self.fields["clasificacion"].queryset = self.fields["clasificacion"].queryset.filter(
                pk=evidencia_clasificacion.pk
            )
            self.fields["clasificacion"].initial = evidencia_clasificacion
            self.fields["clasificacion"].disabled = True

    def clean_comentario(self):
        return _normalize_optional_text(self.cleaned_data.get("comentario"))

    def clean(self):
        cleaned_data = super().clean()
        ciclo = cleaned_data.get("ciclo")
        if ciclo and not cycle_allows_document_upload(ciclo):
            self.add_error(
                "ciclo",
                (
                    "El ciclo seleccionado no habilita la matriz de registro. "
                    "Debe estar APROBADO y contar con su documento de autorizacion en OneDrive."
                ),
            )
        if not cleaned_data.get("clasificacion"):
            self.add_error(
                "clasificacion",
                "No existe una clasificacion activa EVID - Evidencia institucional.",
            )
        return cleaned_data
