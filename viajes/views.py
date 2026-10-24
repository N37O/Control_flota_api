from decimal import Decimal
import json
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Avg, Count
from django.db.utils import OperationalError
from rest_framework.exceptions import ValidationError
from unidades.models import Unidad
from .models import (
    Ubicacion, Cliente, TipoCarga, EstadoViaje, Viaje, Carga, Movimiento,
    RecargaCombustible, PrecioCombustible, PosicionGPS, Alerta,
)
from .serializers import (
    UbicacionSerializer, ClienteSerializer, TipoCargaSerializer,
    EstadoViajeSerializer, ViajeSerializer, ViajeDetalleSerializer,
    CargaSerializer, MovimientoSerializer, RecargaCombustibleSerializer,
    PrecioCombustibleSerializer, PosicionGPSSerializer, AlertaSerializer,
)

def _estado_viaje_id(value):
    estados = {
        'PROGRAMADO': 1,
        'EN_CURSO': 2,
        'EN_TRANSITO': 2,
        'COMPLETADO': 3,
        'CANCELADO': 4,
    }
    normalized = str(value or '').strip().upper()
    if normalized.isdigit() and int(normalized) in (1, 2, 3, 4):
        return int(normalized)
    if normalized in estados:
        return estados[normalized]
    raise ValidationError({
        'estado': 'Usa PROGRAMADO, EN_CURSO/EN_TRANSITO, COMPLETADO o CANCELADO.'
    })


def _validar_transicion_viaje(estado_actual, estado_nuevo):
    transiciones = {
        1: {2, 4},
        2: {3},
        3: set(),
        4: set(),
    }
    if estado_nuevo != estado_actual and estado_nuevo not in transiciones.get(estado_actual, set()):
        raise ValidationError({'estado': 'La transición solicitada no está permitida.'})


def _tipos_unidad_compatibles(tipo_carga):
    compatibles = (tipo_carga.unidades_compatibles or '').strip()
    if not compatibles:
        return set()

    try:
        valores = json.loads(compatibles)
        if not isinstance(valores, list):
            valores = compatibles.replace(';', ',').split(',')
    except (TypeError, ValueError):
        valores = compatibles.replace(';', ',').split(',')

    return {str(valor).strip() for valor in valores if str(valor).strip()}


def _validar_carga_para_viaje(carga, viaje):
    if carga.id_cliente_id and carga.id_cliente_id != viaje.id_cliente_id:
        raise ValidationError(
            f'La carga "{carga.descripcion}" pertenece a otro cliente.'
        )
    if not carga.id_tipo_carga:
        raise ValidationError(
            f'La carga "{carga.descripcion}" debe tener un tipo de carga.'
        )

    compatibles = _tipos_unidad_compatibles(carga.id_tipo_carga)
    if compatibles and str(viaje.id_unidad.id_tipo_unidad_id) not in compatibles:
        raise ValidationError(
            f'La carga "{carga.descripcion}" no es compatible con la unidad '
            f'{viaje.id_unidad.placa}.'
        )


def _validar_viaje_para_inicio(viaje):
    unidad = viaje.id_unidad
    if not unidad.activo:
        raise ValidationError('La unidad del viaje está inactiva.')
    if not unidad.id_conductor_id:
        raise ValidationError('La unidad no tiene un conductor asignado.')
    if not unidad.id_conductor.activo:
        raise ValidationError('El conductor asignado a la unidad está inactivo.')
    if viaje.id_conductor_id != unidad.id_conductor_id:
        raise ValidationError('El conductor del viaje no coincide con el asignado a la unidad.')
    if viaje.id_cliente_id and not viaje.id_cliente.activo:
        raise ValidationError('El cliente asignado al viaje está inactivo.')
    if unidad.id_estado_unidad_id == 2:
        raise ValidationError(f'La unidad {unidad.placa} ya está en otro viaje.')
    if Viaje.objects.filter(
        id_unidad=unidad,
        id_estado_viaje__in=(1, 2),
    ).exclude(pk=viaje.pk).exists():
        raise ValidationError(f'La unidad {unidad.placa} ya tiene otro viaje activo asignado.')

    cargas = list(
        Carga.objects.select_related('id_tipo_carga', 'id_cliente')
        .filter(id_viaje=viaje)
    )
    if not cargas:
        raise ValidationError('No se puede iniciar el viaje sin cargas asignadas.')

    peso_total = Decimal('0')
    for carga in cargas:
        _validar_carga_para_viaje(carga, viaje)
        if carga.peso_ton is None or carga.peso_ton <= 0:
            raise ValidationError(
                f'Indica un peso válido para la carga "{carga.descripcion}" '
                'antes de iniciar el viaje.'
            )
        peso_total += carga.peso_ton

    if peso_total > unidad.capacidad_ton:
        raise ValidationError(
            f'El peso total de las cargas ({peso_total} ton) supera la capacidad '
            f'de la unidad ({unidad.capacidad_ton} ton).'
        )


def _validar_planificacion_viaje(viaje):
    if viaje.id_origen_id == viaje.id_destino_id:
        raise ValidationError({'id_destino': 'El origen y el destino deben ser distintos.'})
    fecha_programada = viaje.fecha_programada or viaje.fecha_salida
    if (
        fecha_programada
        and viaje.fecha_llegada_est
        and viaje.fecha_llegada_est < fecha_programada
    ):
        raise ValidationError({
            'fecha_llegada_est': 'La llegada estimada no puede ser anterior a la salida programada.'
        })


def _validar_lectura_combustible(unidad, galones, requerido=True, exigir_positivo=False):
    capacidad = unidad.capacidad_tanque_gal
    if capacidad is None or capacidad <= 0:
        raise ValidationError({
            'combustible_gal': (
                f'Registra la capacidad del tanque de la unidad {unidad.placa} '
                'antes de iniciar o cerrar un viaje.'
            )
        })
    if galones is None:
        if requerido:
            raise ValidationError({
                'combustible_gal': 'Indica cuánto combustible tiene el tanque.'
            })
        return
    if galones < 0:
        raise ValidationError({
            'combustible_gal': 'La lectura de combustible no puede ser negativa.'
        })
    if exigir_positivo and galones == 0:
        raise ValidationError({
            'combustible_gal': 'La unidad no puede iniciar el viaje con el tanque vacío.'
        })
    if galones > capacidad:
        raise ValidationError({
            'combustible_gal': (
                f'La lectura ({galones} gal) supera la capacidad del tanque '
                f'({capacidad} gal).'
            )
        })


def _asignar_cargas_a_viaje(viaje, ids_cargas):
    if not isinstance(ids_cargas, list):
        raise ValidationError({'cargas': 'Envía las cargas como una lista de identificadores.'})
    if viaje.id_estado_viaje != 1:
        raise ValidationError({'cargas': 'Solo se pueden modificar las cargas de un viaje programado.'})

    ids_normalizados = []
    try:
        ids_normalizados = list(dict.fromkeys(int(id_carga) for id_carga in ids_cargas))
    except (TypeError, ValueError):
        raise ValidationError({'cargas': 'Uno o más identificadores de carga no son válidos.'})

    cargas = list(
        Carga.objects.select_for_update()
        .select_related('id_tipo_carga', 'id_cliente', 'id_viaje')
        .filter(pk__in=ids_normalizados)
    )
    if len(cargas) != len(ids_normalizados):
        raise ValidationError({'cargas': 'Una o más cargas ya no existen.'})

    for carga in cargas:
        if carga.id_viaje_id and carga.id_viaje_id != viaje.pk:
            raise ValidationError(
                {'cargas': f'La carga "{carga.descripcion}" ya está asignada a otro viaje.'}
            )
        _validar_carga_para_viaje(carga, viaje)

    peso_conocido = sum(
        (carga.peso_ton or Decimal('0') for carga in cargas),
        Decimal('0'),
    )
    if peso_conocido > viaje.id_unidad.capacidad_ton:
        raise ValidationError({
            'cargas': (
                f'El peso de las cargas ({peso_conocido} ton) supera la capacidad '
                f'de la unidad ({viaje.id_unidad.capacidad_ton} ton).'
            )
        })

    Carga.objects.filter(id_viaje=viaje).exclude(pk__in=ids_normalizados).update(id_viaje=None)
    if ids_normalizados:
        Carga.objects.filter(pk__in=ids_normalizados).update(id_viaje=viaje)


class UbicacionViewSet(viewsets.ModelViewSet):
    queryset = Ubicacion.objects.filter(activo=True)
    serializer_class = UbicacionSerializer
    permission_classes = [permissions.IsAuthenticated]


class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [permissions.IsAuthenticated]


class TipoCargaViewSet(viewsets.ModelViewSet):
    queryset = TipoCarga.objects.all()
    serializer_class = TipoCargaSerializer
    permission_classes = [permissions.IsAuthenticated]


class EstadoViajeViewSet(viewsets.ModelViewSet):
    queryset = EstadoViaje.objects.all()
    serializer_class = EstadoViajeSerializer
    permission_classes = [permissions.IsAuthenticated]


class ViajeViewSet(viewsets.ModelViewSet):
    queryset = Viaje.objects.all()
    serializer_class = ViajeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ViajeDetalleSerializer
        return ViajeSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        id_unidad = self.request.data.get('id_unidad')
        id_conductor = self.request.data.get('id_conductor')
        kwargs = {}

        if id_unidad:
            try:
                unidad = Unidad.objects.select_for_update().get(id_unidad=id_unidad)
            except Unidad.DoesNotExist:
                raise ValidationError('La unidad seleccionada no es válida.')

            if not unidad.activo:
                raise ValidationError('La unidad seleccionada está inactiva.')
            if unidad.id_estado_unidad_id == 2:
                raise ValidationError(f'La unidad {unidad.placa} ya está en viaje y no puede asignarse a otro.')
            if Viaje.objects.filter(id_unidad=unidad, id_estado_viaje__in=(1, 2)).exists():
                raise ValidationError(f'La unidad {unidad.placa} ya tiene un viaje activo asignado.')
            if not unidad.id_conductor_id:
                raise ValidationError('La unidad seleccionada no tiene un conductor asignado.')
            if not unidad.id_conductor.activo:
                raise ValidationError('El conductor asignado a la unidad está inactivo.')
            if id_conductor and str(id_conductor) != str(unidad.id_conductor_id):
                raise ValidationError('El conductor del viaje debe ser el asignado a la unidad.')
            kwargs['id_conductor'] = unidad.id_conductor

        if serializer.validated_data.get('id_estado_viaje', 1) != 1:
            raise ValidationError('Los viajes nuevos deben crearse como PROGRAMADOS.')

        try:
            viaje = serializer.save(**kwargs, id_estado_viaje=1)
            _validar_planificacion_viaje(viaje)
            if 'cargas' in self.request.data:
                _asignar_cargas_a_viaje(viaje, self.request.data.get('cargas'))
        except OperationalError as e:
            raise ValidationError(str(e))

    @transaction.atomic
    def perform_update(self, serializer):
        id_unidad = self.request.data.get('id_unidad')
        id_conductor = self.request.data.get('id_conductor')
        viaje_original = serializer.instance
        unidad_anterior = viaje_original.id_unidad
        estado_anterior = viaje_original.id_estado_viaje
        kwargs = {}

        if (
            estado_anterior == 2
            and id_unidad
            and str(id_unidad) != str(unidad_anterior.pk)
        ):
            raise ValidationError('No se puede cambiar la unidad de un viaje que ya inició.')

        if id_unidad:
            try:
                unidad_nueva = Unidad.objects.select_for_update().get(id_unidad=id_unidad)
            except Unidad.DoesNotExist:
                raise ValidationError('La unidad seleccionada no es válida.')

            if not unidad_nueva.activo:
                raise ValidationError('La unidad seleccionada está inactiva.')
            if unidad_nueva.id_estado_unidad_id == 2 and unidad_nueva.pk != unidad_anterior.pk:
                raise ValidationError(f'La unidad {unidad_nueva.placa} ya está en viaje.')
            if Viaje.objects.filter(
                id_unidad=unidad_nueva,
                id_estado_viaje__in=(1, 2),
            ).exclude(pk=viaje_original.pk).exists():
                raise ValidationError(f'La unidad {unidad_nueva.placa} ya tiene otro viaje activo asignado.')
            if not unidad_nueva.id_conductor_id:
                raise ValidationError('La unidad seleccionada no tiene un conductor asignado.')
            if not unidad_nueva.id_conductor.activo:
                raise ValidationError('El conductor asignado a la unidad está inactivo.')
            if id_conductor and str(id_conductor) != str(unidad_nueva.id_conductor_id):
                raise ValidationError('El conductor del viaje debe ser el asignado a la unidad.')
            kwargs['id_conductor'] = unidad_nueva.id_conductor

        conductor_nuevo = serializer.validated_data.get('id_conductor')
        unidad_validada = serializer.validated_data.get('id_unidad', unidad_anterior)
        if conductor_nuevo and conductor_nuevo.pk != unidad_validada.id_conductor_id:
            raise ValidationError('El conductor del viaje debe ser el asignado a la unidad.')

        estado_nuevo = serializer.validated_data.get('id_estado_viaje', estado_anterior)
        if (estado_anterior, estado_nuevo) == (2, 4):
            raise ValidationError({
                'estado': 'Un viaje en curso debe registrar su llegada desde Control antes de cancelarse.'
            })
        _validar_transicion_viaje(estado_anterior, estado_nuevo)
        if (estado_anterior, estado_nuevo) in ((1, 2), (2, 3)):
            raise ValidationError({
                'estado': 'Registra la salida o llegada desde Control para guardar el movimiento y el odómetro.'
            })
        viaje = serializer.save(**kwargs)
        _validar_planificacion_viaje(viaje)
        if 'cargas' in self.request.data:
            _asignar_cargas_a_viaje(viaje, self.request.data.get('cargas'))

        if estado_anterior == 2 and viaje.id_unidad_id != unidad_anterior.pk:
            unidad_anterior.id_estado_unidad_id = 1
            unidad_anterior.save(update_fields=['id_estado_unidad_id'])

        if viaje.id_estado_viaje == 2:
            if not viaje.fecha_salida:
                viaje.fecha_salida = timezone.now()
                viaje.save(update_fields=['fecha_salida'])
            viaje.id_unidad.id_estado_unidad_id = 2
            viaje.id_unidad.save(update_fields=['id_estado_unidad_id'])
        elif viaje.id_estado_viaje == 3:
            if viaje.id_estado_viaje == 3 and not viaje.fecha_llegada_real:
                viaje.fecha_llegada_real = timezone.now()
                viaje.save(update_fields=['fecha_llegada_real'])
            viaje.id_unidad.id_estado_unidad_id = 1
            viaje.id_unidad.save(update_fields=['id_estado_unidad_id'])
        elif viaje.id_estado_viaje == 4 and estado_anterior == 1:
            Carga.objects.filter(id_viaje=viaje).update(id_viaje=None)
    @transaction.atomic
    def perform_destroy(self, instance):
        """Al eliminar un viaje, liberar automáticamente la unidad y las cargas asociadas"""
        if instance.id_estado_viaje == 2:
            raise ValidationError('No se puede eliminar un viaje que está en curso.')

        # Liberar las cargas asociadas a este viaje.
        Carga.objects.filter(id_viaje=instance).update(id_viaje=None)

        instance.delete()

    @action(detail=True, methods=['post'], url_path='cambiar-estado')
    @transaction.atomic
    def cambiar_estado(self, request, pk=None):
        viaje = Viaje.objects.select_for_update().select_related(
            'id_unidad__id_conductor', 'id_cliente'
        ).get(pk=self.get_object().pk)
        nuevo_estado = request.data.get('estado')

        nuevo_id_estado = _estado_viaje_id(nuevo_estado)
        estado_anterior = viaje.id_estado_viaje
        if (estado_anterior, nuevo_id_estado) == (2, 4):
            raise ValidationError({
                'estado': 'Un viaje en curso debe registrar su llegada desde Control antes de cancelarse.'
            })
        _validar_transicion_viaje(estado_anterior, nuevo_id_estado)

        if nuevo_id_estado in (2, 3):
            raise ValidationError({
                'estado': 'Registra la salida o llegada desde Control para guardar el movimiento y el odómetro.'
            })

        viaje.id_estado_viaje = nuevo_id_estado

        viaje.save()
        if nuevo_id_estado == 4 and estado_anterior == 1:
            Carga.objects.filter(id_viaje=viaje).update(id_viaje=None)

        serializer = self.get_serializer(viaje)
        return Response(serializer.data)

class CargaViewSet(viewsets.ModelViewSet):
    queryset = Carga.objects.all()
    serializer_class = CargaSerializer
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def perform_create(self, serializer):
        carga = serializer.save()
        if carga.id_viaje_id:
            viaje = Viaje.objects.select_for_update().select_related(
                'id_unidad__id_tipo_unidad'
            ).get(pk=carga.id_viaje_id)
            if viaje.id_estado_viaje != 1:
                raise ValidationError('Solo se pueden asignar cargas a viajes programados.')
            _validar_carga_para_viaje(carga, viaje)

    @transaction.atomic
    def perform_update(self, serializer):
        carga_original = serializer.instance
        if carga_original.id_viaje_id:
            viaje_original = Viaje.objects.select_for_update().get(pk=carga_original.id_viaje_id)
            if viaje_original.id_estado_viaje != 1:
                raise ValidationError('No se pueden modificar cargas de un viaje que ya inició.')

        carga = serializer.save()
        if carga.id_viaje_id:
            viaje = Viaje.objects.select_for_update().select_related(
                'id_unidad__id_tipo_unidad'
            ).get(pk=carga.id_viaje_id)
            if viaje.id_estado_viaje != 1:
                raise ValidationError('Solo se pueden asignar cargas a viajes programados.')
            _validar_carga_para_viaje(carga, viaje)

class MovimientoViewSet(viewsets.ModelViewSet):
    queryset = Movimiento.objects.all().order_by('-fecha_hora')
    serializer_class = MovimientoSerializer
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def perform_create(self, serializer):
        datos = serializer.validated_data
        datos['fecha_hora'] = timezone.now()
        if datos.get('odometro_km') is not None and datos['odometro_km'] < 0:
            raise ValidationError({'odometro_km': 'El odómetro no puede ser negativo.'})
        if datos.get('combustible_gal') is not None and datos['combustible_gal'] < 0:
            raise ValidationError({'combustible_gal': 'El combustible no puede ser negativo.'})
        unidad = Unidad.objects.select_for_update().get(pk=datos['id_unidad'].pk)
        viaje = datos.get('id_viaje')
        if viaje:
            viaje = Viaje.objects.select_for_update().select_related(
                'id_unidad__id_conductor', 'id_unidad__id_tipo_unidad',
                'id_conductor', 'id_origen', 'id_destino', 'id_cliente',
            ).get(pk=viaje.pk)
            if viaje.id_unidad_id != unidad.pk:
                raise ValidationError({'id_unidad': 'La unidad debe coincidir con la unidad asignada al viaje.'})
            if datos['tipo'] == 'SALIDA':
                if viaje.id_estado_viaje != 1:
                    raise ValidationError({'id_viaje': 'Solo se puede registrar la salida de un viaje programado.'})
                _validar_viaje_para_inicio(viaje)
                if datos.get('id_ubicacion').pk != viaje.id_origen_id:
                    raise ValidationError({'id_ubicacion': 'La salida debe registrarse desde el origen del viaje.'})
            elif datos['tipo'] == 'ENTRADA':
                if viaje.id_estado_viaje != 2:
                    raise ValidationError({'id_viaje': 'Solo se puede registrar la entrada de un viaje en curso.'})
                if datos.get('id_ubicacion').pk != viaje.id_destino_id:
                    raise ValidationError({'id_ubicacion': 'La entrada debe registrarse en el destino del viaje.'})
                if not viaje.fecha_salida or datos['fecha_hora'] < viaje.fecha_salida:
                    raise ValidationError({'fecha_hora': 'La entrada no puede ser anterior a la salida del viaje.'})
                if viaje.combustible_inicial_gal is None:
                    raise ValidationError({
                        'combustible_gal': 'El viaje no tiene una lectura de combustible registrada al salir.'
                    })
            if datos.get('odometro_km') is None:
                raise ValidationError({'odometro_km': 'El odómetro es obligatorio para iniciar o finalizar un viaje.'})
            _validar_lectura_combustible(
                unidad,
                datos.get('combustible_gal'),
                requerido=True,
                exigir_positivo=datos['tipo'] == 'SALIDA',
            )
            if unidad.odometro_actual is not None and datos['odometro_km'] < unidad.odometro_actual:
                raise ValidationError({'odometro_km': 'El odómetro no puede ser menor al último registro de la unidad.'})
            if datos['tipo'] == 'ENTRADA' and viaje.odometro_inicial is not None:
                if datos['odometro_km'] < viaje.odometro_inicial:
                    raise ValidationError({'odometro_km': 'El odómetro de llegada no puede ser menor al de salida.'})
            if datos['tipo'] == 'ENTRADA':
                recargas_en_ruta = RecargaCombustible.objects.filter(
                    id_viaje=viaje,
                    fecha_hora__gt=viaje.fecha_salida,
                    fecha_hora__lte=datos['fecha_hora'],
                ).aggregate(total=Sum('galones'))['total'] or Decimal('0.00')
                combustible_disponible = viaje.combustible_inicial_gal + recargas_en_ruta
                if datos['combustible_gal'] > combustible_disponible:
                    raise ValidationError({
                        'combustible_gal': (
                            'La lectura al llegar no puede superar el combustible de '
                            'salida más las recargas hechas durante el viaje.'
                        )
                    })
            movimiento = serializer.save(
                id_unidad=unidad,
                id_viaje=viaje,
                id_conductor=viaje.id_conductor,
            )
        else:
            movimiento = serializer.save(id_unidad=unidad)

        if movimiento.odometro_km is not None:
            unidad.odometro_actual = movimiento.odometro_km
        campos_unidad_actualizados = []
        if movimiento.odometro_km is not None:
            campos_unidad_actualizados.append('odometro_actual')
        if movimiento.combustible_gal is not None:
            unidad.combustible_actual_gal = movimiento.combustible_gal
            unidad.fecha_combustible_actual = movimiento.fecha_hora
            campos_unidad_actualizados.extend([
                'combustible_actual_gal',
                'fecha_combustible_actual',
            ])
        if campos_unidad_actualizados:
            unidad.save(update_fields=campos_unidad_actualizados)

        if not viaje:
            return

        if movimiento.tipo == 'SALIDA':
            viaje.id_estado_viaje = 2
            viaje.combustible_inicial_gal = movimiento.combustible_gal
            viaje.combustible_salida_gal = movimiento.combustible_gal
            viaje.odometro_inicial = movimiento.odometro_km
            viaje.odometro_salida = movimiento.odometro_km
            viaje.fecha_salida = movimiento.fecha_hora
            viaje.save()
            unidad.id_estado_unidad_id = 2
            unidad.save(update_fields=['id_estado_unidad_id'])
        elif movimiento.tipo == 'ENTRADA':
            viaje.combustible_final_gal = movimiento.combustible_gal
            viaje.combustible_llegada_gal = movimiento.combustible_gal
            viaje.odometro_final = movimiento.odometro_km
            viaje.odometro_llegada = movimiento.odometro_km
            viaje.fecha_llegada_real = movimiento.fecha_hora

            if viaje.odometro_inicial is not None:
                viaje.km_recorridos = viaje.odometro_final - viaje.odometro_inicial

            if viaje.combustible_inicial_gal is not None and viaje.combustible_final_gal is not None:
                recargas_qs = RecargaCombustible.objects.filter(id_viaje=viaje)
                recargas_en_ruta = recargas_qs.filter(
                    fecha_hora__gt=viaje.fecha_salida,
                    fecha_hora__lte=movimiento.fecha_hora,
                )
                total_galones_recargados = recargas_en_ruta.aggregate(
                    total=Sum('galones')
                )['total'] or Decimal('0.00')
                viaje.galones_consumidos = (
                    viaje.combustible_inicial_gal
                    - viaje.combustible_final_gal
                    + total_galones_recargados
                )
                viaje.costo_combustible = sum(
                    (
                        recarga.galones * recarga.precio_galon
                        for recarga in recargas_qs
                    ),
                    Decimal('0.00'),
                )

            if viaje.km_recorridos and viaje.galones_consumidos and viaje.galones_consumidos > 0:
                viaje.rendimiento_km_gal = round(
                    float(viaje.km_recorridos) / float(viaje.galones_consumidos), 2
                )
                viaje.alerta_consumo = viaje.rendimiento_km_gal < 8.0

            viaje.id_estado_viaje = 3
            viaje.save()
            unidad.id_estado_unidad_id = 1
            unidad.save(update_fields=['id_estado_unidad_id'])

    @action(detail=False, methods=['post'])
    def registrar_salida(self, request):
        if request.data.get('tipo') != 'SALIDA':
            raise ValidationError({'tipo': 'Este endpoint solo registra movimientos de SALIDA.'})
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def registrar_entrada(self, request):
        if request.data.get('tipo') != 'ENTRADA':
            raise ValidationError({'tipo': 'Este endpoint solo registra movimientos de ENTRADA.'})
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class PrecioCombustibleViewSet(viewsets.ModelViewSet):
    queryset = PrecioCombustible.objects.all().order_by('-vigente_desde')
    serializer_class = PrecioCombustibleSerializer
    permission_classes = [permissions.IsAuthenticated]


class RecargaCombustibleViewSet(viewsets.ModelViewSet):
    queryset = RecargaCombustible.objects.all().order_by('-fecha_hora')
    serializer_class = RecargaCombustibleSerializer
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def perform_create(self, serializer):
        datos = serializer.validated_data
        viaje = datos.get('id_viaje')
        unidad_id = datos.get('id_unidad')
        if not unidad_id and viaje:
            unidad_id = viaje.id_unidad
        if not unidad_id:
            raise ValidationError({'id_unidad': 'Selecciona la unidad que recibió el combustible.'})

        unidad = Unidad.objects.select_for_update().get(pk=unidad_id.pk)
        if viaje:
            viaje = Viaje.objects.select_for_update().select_related('id_unidad').get(pk=viaje.pk)
            if viaje.id_unidad_id != unidad.pk:
                raise ValidationError({'id_unidad': 'La unidad no coincide con la unidad asignada al viaje.'})
            if viaje.id_estado_viaje not in (1, 2):
                raise ValidationError({'id_viaje': 'Solo se pueden asociar recargas a viajes programados o en curso.'})

        viaje_en_curso_id = Viaje.objects.select_for_update().filter(
            id_unidad=unidad,
            id_estado_viaje=2,
        ).values_list('pk', flat=True).first()
        if viaje_en_curso_id and (not viaje or viaje.pk != viaje_en_curso_id):
            raise ValidationError({
                'id_viaje': 'Selecciona el viaje en curso para asociar esta recarga.'
            })

        if datos['galones'] <= 0:
            raise ValidationError({'galones': 'Los galones deben ser mayores a cero.'})
        if datos['precio_galon'] <= 0:
            raise ValidationError({'precio_galon': 'El precio por galón debe ser mayor a cero.'})
        capacidad = unidad.capacidad_tanque_gal
        if capacidad is None or capacidad <= 0:
            raise ValidationError({
                'galones': 'Registra primero la capacidad del tanque en la unidad.'
            })
        if datos['galones'] > capacidad:
            raise ValidationError({
                'galones': (
                    'La cantidad de la recarga no puede superar la capacidad del tanque '
                    'de la unidad. Verifica también cuánto espacio queda en el tanque.'
                )
            })
        nivel_tanque = datos['nivel_tanque_gal']
        if nivel_tanque <= 0 or nivel_tanque < datos['galones']:
            raise ValidationError({
                'nivel_tanque_gal': (
                    'Indica el nivel real después de cargar; debe ser al menos igual '
                    'a los galones comprados.'
                )
            })
        if nivel_tanque > capacidad:
            raise ValidationError({
                'nivel_tanque_gal': 'El nivel después de cargar no puede superar la capacidad del tanque.'
            })
        if datos['fecha_hora'] > timezone.now():
            raise ValidationError({'fecha_hora': 'La fecha de la recarga no puede estar en el futuro.'})
        if viaje and viaje.id_estado_viaje == 2:
            if not viaje.fecha_salida:
                raise ValidationError({
                    'id_viaje': 'El viaje en curso no tiene una hora de salida registrada.'
                })
            if datos['fecha_hora'] < viaje.fecha_salida:
                raise ValidationError({'fecha_hora': 'La recarga de un viaje en curso no puede ser anterior a la salida.'})
        recarga = serializer.save(id_unidad=unidad, id_viaje=viaje)
        unidad.combustible_actual_gal = nivel_tanque
        unidad.fecha_combustible_actual = recarga.fecha_hora
        unidad.save(update_fields=['combustible_actual_gal', 'fecha_combustible_actual'])

        # Calcular el total de galones recargados para el viaje.
        if recarga.id_viaje:
            viaje = recarga.id_viaje
            total_recargas = RecargaCombustible.objects.filter(
                id_viaje=viaje
            ).aggregate(total=Sum('galones'))['total'] or 0

            # Si el viaje tiene un campo para este total, puede actualizarse aquí.
class PosicionGPSViewSet(viewsets.ModelViewSet):
    queryset = PosicionGPS.objects.order_by('-fecha_hora')
    serializer_class = PosicionGPSSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['id_dispositivo', 'id_viaje']
    ordering_fields = ['fecha_hora', 'velocidad_kmh']
    ordering = ['-fecha_hora']

    @action(detail=False, methods=['post'])
    def actualizar_posicion(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class AlertaViewSet(viewsets.ModelViewSet):
    queryset = Alerta.objects.all()
    serializer_class = AlertaSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def pendientes(self, request):
        alertas = self.queryset.filter(atendida=False)
        serializer = self.get_serializer(alertas, many=True)
        return Response(serializer.data)

        