import os
import uuid

from django.core.files.storage import default_storage
from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef
from rest_framework import viewsets, status, permissions, parsers
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from viajes.models import Viaje
from .models import (TipoUnidad, EstadoUnidad, Unidad, DispositivoGPS, 
                     Conductor, AsignacionUnidad, Mantenimiento)
from .serializers import (TipoUnidadSerializer, EstadoUnidadSerializer, 
                          UnidadSerializer, DispositivoGPSSerializer,
                          ConductorSerializer, AsignacionUnidadSerializer,
                          MantenimientoSerializer)

class TipoUnidadViewSet(viewsets.ModelViewSet):
    queryset = TipoUnidad.objects.all()
    serializer_class = TipoUnidadSerializer
    permission_classes = [permissions.IsAuthenticated]

class EstadoUnidadViewSet(viewsets.ModelViewSet):
    queryset = EstadoUnidad.objects.all()
    serializer_class = EstadoUnidadSerializer
    permission_classes = [permissions.IsAuthenticated]

class UnidadViewSet(viewsets.ModelViewSet):
    queryset = Unidad.objects.order_by('pk').annotate(
        tiene_viaje_activo=Exists(
            Viaje.objects.filter(
                id_unidad=OuterRef('pk'),
                id_estado_viaje__in=(1, 2),
            )
        ),
    )
    serializer_class = UnidadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def update(self, request, *args, **kwargs):
        """Sobrescribir update para garantizar que id_conductor=None se guarde"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        # Forzar que si viene 'null' o vacío, sea None real de Python
        if 'id_conductor' in request.data:
            if request.data['id_conductor'] is None or str(request.data['id_conductor']).strip().lower() in ['null', '']:
                request.data['id_conductor'] = None

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='quitar-conductor')
    def quitar_conductor(self, request, pk=None):
        """Acción directa para quitar el conductor sin pasar por el serializer"""
        try:
            unidad = self.get_object()
            unidad.id_conductor = None
            unidad.save(update_fields=['id_conductor'])
            return Response(
                {'status': 'success', 'message': 'Conductor desasignado'},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {'status': 'error', 'message': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class DispositivoGPSViewSet(viewsets.ModelViewSet):
    queryset = DispositivoGPS.objects.all()
    serializer_class = DispositivoGPSSerializer
    permission_classes = [permissions.IsAuthenticated]

class ConductorViewSet(viewsets.ModelViewSet):
    queryset = Conductor.objects.all()
    serializer_class = ConductorSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.FormParser, parsers.MultiPartParser, parsers.JSONParser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['activo']

    @staticmethod
    def _guardar_licencia_imagen(file_obj):
        if not file_obj:
            return None

        nombre = file_obj.name or 'licencia'
        extension = os.path.splitext(nombre)[1].lower()
        if extension not in ['.jpg', '.jpeg', '.png']:
            raise ValidationError('La imagen de la licencia debe ser JPG o PNG.')

        folder = 'conductores/licencias'
        nombre_archivo = f"{uuid.uuid4().hex}{extension}"
        ruta = default_storage.save(os.path.join(folder, nombre_archivo), file_obj)
        return ruta

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        imagen = request.FILES.get('licencia_imagen')

        if imagen and getattr(imagen, 'name', None):
            data['licencia_imagen'] = self._guardar_licencia_imagen(imagen)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        data = request.data.copy()
        imagen = request.FILES.get('licencia_imagen')

        if imagen and getattr(imagen, 'name', None):
            data['licencia_imagen'] = self._guardar_licencia_imagen(imagen)

        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

class AsignacionUnidadViewSet(viewsets.ModelViewSet):
    queryset = AsignacionUnidad.objects.all()
    serializer_class = AsignacionUnidadSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['post'])
    def asignar(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class MantenimientoViewSet(viewsets.ModelViewSet):
    queryset = Mantenimiento.objects.all()
    serializer_class = MantenimientoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id_unidad', 'tipo']