from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'ubicaciones', views.UbicacionViewSet)
router.register(r'clientes', views.ClienteViewSet)
router.register(r'tipos-carga', views.TipoCargaViewSet)
router.register(r'estados-viaje', views.EstadoViajeViewSet)
router.register(r'viajes', views.ViajeViewSet)
router.register(r'cargas', views.CargaViewSet)
router.register(r'movimientos', views.MovimientoViewSet)
router.register(r'recargas', views.RecargaCombustibleViewSet)
router.register(r'posiciones-gps', views.PosicionGPSViewSet)
router.register(r'alertas', views.AlertaViewSet)

urlpatterns = [
    path('', include(router.urls)),
]