from django.urls import path
from . import views

urlpatterns = [
    path('panel/', views.PanelFlotaView.as_view(), name='panel-flota'),
    path('rendimiento/', views.RendimientoView.as_view(), name='rendimiento'),
    path('historial/', views.HistorialView.as_view(), name='historial'),
]