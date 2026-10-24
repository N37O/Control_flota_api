from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'tipos', views.TipoUnidadViewSet)
router.register(r'estados', views.EstadoUnidadViewSet)
router.register(r'unidades', views.UnidadViewSet)
router.register(r'gps', views.DispositivoGPSViewSet)
router.register(r'conductores', views.ConductorViewSet)
router.register(r'asignaciones', views.AsignacionUnidadViewSet)
router.register(r'mantenimientos', views.MantenimientoViewSet)

urlpatterns = [
    path('', include(router.urls)),
]