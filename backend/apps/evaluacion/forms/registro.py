from django import forms

from apps.documentos.forms import StructuredDocumentUploadForm
from apps.documentos.selectors import cycle_allows_document_upload


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = " ".join((value or "").strip().split())
    return normalized or None


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
        return cleaned_data
