from django.urls import path

from apps.documentos.views.web import (
    AuthorizationCycleView,
    DocumentAccessLogListView,
    DocumentClassificationListView,
    DocumentDetailView,
    DocumentListView,
    DocumentVersionListView,
    DocumentUploadView,
    DocxLaboratoryView,
    ProtectedDocumentAccessView,
    ProtectedDocumentAvailabilityView,
    ProtectedDocumentDownloadView,
    ProtectedDocumentGraphRedirectView,
    ProtectedDocumentPreviewView,
    module_page,
)

urlpatterns = [
    path('clasificaciones/', DocumentClassificationListView.as_view(), name='documentos-clasificaciones-lista'),
    path('', DocumentListView.as_view(), name='documentos-lista'),
    path('subir/', DocumentUploadView.as_view(), name='documentos-subir'),
    path('detalle/', DocumentDetailView.as_view(), name='documentos-detalle'),
    path('versiones/', DocumentVersionListView.as_view(), name='documentos-versiones'),
    path('accesos/', DocumentAccessLogListView.as_view(), name='documentos-accesos'),
    path('laboratorio-docx/', DocxLaboratoryView.as_view(), name='documentos-docx-lab'),
    path('protegidos/<int:documento_id>/validar/', ProtectedDocumentAvailabilityView.as_view(), name='documentos-protegidos-validar'),
    path('protegidos/<int:documento_id>/abrir/', ProtectedDocumentAccessView.as_view(), name='documentos-protegidos-abrir'),
    path('protegidos/<int:documento_id>/descargar/', ProtectedDocumentDownloadView.as_view(), name='documentos-protegidos-descargar'),
    path('protegidos/<int:documento_id>/preview/', ProtectedDocumentPreviewView.as_view(), name='documentos-protegidos-preview'),
    path('protegidos/<int:documento_id>/graph/', ProtectedDocumentGraphRedirectView.as_view(), name='documentos-protegidos-graph'),
    path('autorizacion-ciclo/', AuthorizationCycleView.as_view(), name='documentos-autorizacion-ciclo'),
]
