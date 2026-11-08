from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from viajes.views import PrecioCombustibleViewSet, RecargaCombustibleViewSet, MovimientoViewSet

router = DefaultRouter()
router.register(r'control/precios-combustible', PrecioCombustibleViewSet, basename='precios-combustible')
router.register(r'control/recargas', RecargaCombustibleViewSet, basename='recargas')
router.register(r'control/movimientos', MovimientoViewSet, basename='movimientos')

# Vista simple para la raíz
def inicio_api(request):
    return JsonResponse({
        "mensaje": "Bienvenido a la API del Sistema de Gestión de Flotas",
        "version": "1.0"
    })

urlpatterns = [
    path('', inicio_api),
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path(
        'swagger/',
        SpectacularSwaggerView.as_view(url_name='schema'),
        name='swagger-ui',
    ),
    path(
        'redoc/',
        SpectacularRedocView.as_view(url_name='schema'),
        name='redoc',
    ),
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/usuarios/', include('usuarios.urls')),
    path('api/unidades/', include('unidades.urls')),
    path('api/viajes/', include('viajes.urls')),
    path('api/reportes/', include('reportes.urls')),
]