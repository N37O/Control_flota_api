from rest_framework import views, permissions, status
from rest_framework.response import Response
from django.db.models import Avg, DecimalField, ExpressionWrapper, F, Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from viajes.models import Viaje
from unidades.models import Unidad

class PanelFlotaView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        unidades_disponibles = Unidad.objects.filter(
            id_estado_unidad__nombre__iexact='DISPONIBLE', activo=True
        ).count()
        
        unidades_transito = Unidad.objects.filter(
            Q(id_estado_unidad__nombre__iexact='En viaje')
            | Q(id_estado_unidad__nombre__iexact='EN_VIAJE'),
            activo=True,
        ).count()
        
        viajes_programados = Viaje.objects.filter(id_estado_viaje=1).count()
        
        viajes_transito = Viaje.objects.filter(id_estado_viaje=2).count()
        
        alertas_pendientes = Viaje.objects.filter(
            id_estado_viaje=2,
            fecha_llegada_est__lt=timezone.now()
        ).count()

        return Response({
            'unidades_disponibles': unidades_disponibles,
            'unidades_transito': unidades_transito,
            'viajes_programados': viajes_programados,
            'viajes_transito': viajes_transito,
            'alertas_pendientes': alertas_pendientes,
        })

class RendimientoView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        viajes = Viaje.objects.filter(
            id_estado_viaje=3,
            km_recorridos__gt=0,
            galones_consumidos__gt=0,
        ).annotate(
            rendimiento=ExpressionWrapper(
                F('km_recorridos') / F('galones_consumidos'),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        )

        rendimiento_promedio = viajes.aggregate(
            avg_rendimiento=Avg('rendimiento')
        )['avg_rendimiento']

        return Response({
            'rendimiento_promedio': round(rendimiento_promedio, 2) if rendimiento_promedio else 0,
            'total_viajes': viajes.count()
        })

class HistorialView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        viajes = Viaje.objects.all().select_related(
            'id_unidad', 'id_conductor', 'id_origen', 'id_destino'
        ).order_by('-fecha_salida', '-creado_en')
        
        # Filtros
        if request.query_params.get('unidad'):
            viajes = viajes.filter(id_unidad=request.query_params.get('unidad'))
        if request.query_params.get('conductor'):
            viajes = viajes.filter(id_conductor=request.query_params.get('conductor'))
        estado = request.query_params.get('estado')
        if estado:
            try:
                viajes = viajes.filter(id_estado_viaje=int(estado))
            except ValueError:
                return Response(
                    {'estado': 'El estado debe ser un número entre 1 y 4.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        for parameter, lookup in (
            ('desde', 'fecha_salida__date__gte'),
            ('hasta', 'fecha_salida__date__lte'),
        ):
            value = request.query_params.get(parameter)
            if value:
                parsed_date = parse_date(value)
                if not parsed_date:
                    return Response(
                        {parameter: 'Usa el formato YYYY-MM-DD.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                viajes = viajes.filter(**{lookup: parsed_date})

        busqueda = request.query_params.get('buscar', '').strip()
        if busqueda:
            viajes = viajes.filter(
                Q(correlativo__icontains=busqueda)
                | Q(id_unidad__placa__icontains=busqueda)
                | Q(id_conductor__nombre__icontains=busqueda)
                | Q(id_origen__nombre__icontains=busqueda)
                | Q(id_destino__nombre__icontains=busqueda)
            )

        nombres_estado = {
            1: 'PROGRAMADO',
            2: 'EN_CURSO',
            3: 'COMPLETADO',
            4: 'CANCELADO',
        }
        
        serializer_data = []
        for viaje in viajes[:50]:
            serializer_data.append({
                'correlativo': viaje.correlativo,
                'unidad': viaje.id_unidad.placa,
                'conductor': viaje.id_conductor.nombre,
                'origen': viaje.id_origen.nombre,
                'destino': viaje.id_destino.nombre,
                'estado': nombres_estado.get(viaje.id_estado_viaje, 'DESCONOCIDO'),
                'fecha_salida': viaje.fecha_salida,
                'fecha_llegada_est': viaje.fecha_llegada_est,
                'fecha_llegada_real': viaje.fecha_llegada_real,
            })
        
        return Response(serializer_data)