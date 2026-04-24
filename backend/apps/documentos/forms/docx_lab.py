from django import forms

from apps.core.services.upload_security import validate_uploaded_file


class DocxLaboratoryForm(forms.Form):
    archivo = forms.FileField(label="Archivo DOCX")

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        validate_uploaded_file(archivo, label="archivo DOCX")
        nombre_archivo = (getattr(archivo, "name", "") or "").strip().lower()
        if not nombre_archivo.endswith(".docx"):
            raise forms.ValidationError("Solo se permite archivo DOCX para este laboratorio.")
        return archivo