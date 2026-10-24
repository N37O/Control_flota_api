from decimal import Decimal

from rest_framework import serializers
from unidades.models import DispositivoGPS, Unidad
from .models import (Ubicacion, Cliente, TipoCarga, EstadoViaje, Viaje, 
                     Carga, Movimiento, PrecioCombustible, RecargaCombustible,
                     PosicionGPS, Alerta)


def _validar_geometria_polyline(geometria):
    if len(geometria) > 100000:
        raise serializers.ValidationError(
            'La geometría de la ruta supera el tamaño permitido.'
        )

    indice = 0
    latitud = 0
    longitud = 0
    puntos = 0

    try:
        while indice < len(geometria):
            incrementos = []
            for _ in range(2):
                resultado = 0
                desplazamiento = 0
                while True:
                    if indice >= len(geometria):
                        raise ValueError
                    byte = ord(geometria[indice]) - 63
                    indice += 1
                    if not 0 <= byte <= 63:
                        raise ValueError
                    resultado |= (byte & 0x1f) << desplazamiento
                    desplazamiento += 5
                    if desplazamiento > 30:
                        raise ValueError
                    if byte < 0x20:
                        break

                incremento = (
                    ~(resultado >> 1)
                    if resultado & 1
                    else resultado >> 1
                )
                incrementos.append(incremento)

            latitud += incrementos[0]
            longitud += incrementos[1]
            if not -9000000 <= latitud <= 9000000:
                raise ValueError
            if not -18000000 <= longitud <= 18000000:
                raise ValueError
            puntos += 1
    except ValueError:
        raise serializers.ValidationError(
            'La geometría de la ruta no tiene un formato válido.'
        )

    if puntos < 2:
        raise serializers.ValidationError(
            'La geometría de la ruta debe incluir al menos dos puntos.'
        )


class UbicacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ubicacion
        fields = '__all__'

class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = [
            'id_cliente', 'nombre', 'nombre_comercial',
            'tipo_cliente', 'documento',
            'nit', 'contacto', 'telefono', 'correo', 'direccion', 'activo'
        ]
        extra_kwargs = {
            'nombre_comercial': {'required': False, 'allow_null': True},
            'tipo_cliente': {'required': False, 'allow_null': True},
            'documento': {'required': False, 'allow_null': True},
            'nit': {'required': False, 'allow_null': True},
            'contacto': {'required': False, 'allow_null': True},
            'correo': {'required': False, 'allow_null': True}
        }

class TipoCargaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoCarga
        fields = [
            'id_tipo_carga', 'nombre', 'unidades_compatibles'
        ]

class EstadoViajeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EstadoViaje
        fields = '__all__'

class CargaSerializer(serializers.ModelSerializer):
    viaje_correlativo = serializers.CharField(source='id_viaje.correlativo', read_only=True, allow_null=True)
    tipo_carga_nombre = serializers.CharField(source='id_tipo_carga.nombre', read_only=True, allow_null=True)
    cliente_nombre = serializers.CharField(source='id_cliente.nombre', read_only=True, allow_null=True)
    unidades_compatibles = serializers.CharField(source='id_tipo_carga.unidades_compatibles', read_only=True, allow_null=True)

    class Meta:
        model = Carga
        fields = [
            'id_carga', 'id_viaje', 'id_tipo_carga', 'id_cliente',
            'descripcion', 'cantidad', 'unidad_medida', 'peso_ton', 'documento_ref',
            'viaje_correlativo', 'tipo_carga_nombre', 'cliente_nombre', 'unidades_compatibles'
        ]

class PrecioCombustibleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrecioCombustible
        fields = '__all__'

class RecargaCombustibleSerializer(serializers.ModelSerializer):
    id_unidad = serializers.PrimaryKeyRelatedField(
        queryset=Unidad.objects.all(),
        required=True,
    )
    nivel_tanque_gal = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        required=True,
    )
    viaje_correlativo = serializers.CharField(
        source='id_viaje.correlativo',
        read_only=True,
        allow_null=True,
    )
    unidad_placa = serializers.CharField(source='id_unidad.placa', read_only=True)

    class Meta:
        model = RecargaCombustible
        fields = [
            'id_recarga', 'id_viaje', 'id_unidad', 'fecha_hora', 'galones',
            'nivel_tanque_gal',
            'precio_galon', 'lugar', 'numero_factura',
            'viaje_correlativo', 'unidad_placa'
        ]
        extra_kwargs = {
            'id_viaje': {'required': False, 'allow_null': True},
        }

class MovimientoSerializer(serializers.ModelSerializer):
    unidad_placa = serializers.CharField(source='id_unidad.placa', read_only=True)
    conductor_nombre = serializers.CharField(source='id_conductor.nombre', read_only=True, allow_null=True)
    ubicacion_nombre = serializers.CharField(source='id_ubicacion.nombre', read_only=True)
    viaje_correlativo = serializers.CharField(source='id_viaje.correlativo', read_only=True, allow_null=True)

    class Meta:
        model = Movimiento
        fields = [
            'id_movimiento', 'id_viaje', 'id_unidad', 'id_conductor',
            'id_ubicacion', 'tipo', 'fecha_hora', 'combustible_gal',
            'odometro_km', 'observacion',
            'unidad_placa', 'conductor_nombre', 'ubicacion_nombre', 'viaje_correlativo'
        ]
        read_only_fields = ['fecha_hora']
        extra_kwargs = {
            'id_viaje': {'required': False, 'allow_null': True},
            'id_conductor': {'required': False, 'allow_null': True},
            'combustible_gal': {'required': False, 'allow_null': True},
            'odometro_km': {'required': False, 'allow_null': True},
            'observacion': {'required': False, 'allow_null': True},
        }

class PosicionGPSSerializer(serializers.ModelSerializer):
    id_dispositivo = serializers.PrimaryKeyRelatedField(
        queryset=DispositivoGPS.objects.only('id_dispositivo')
    )
    latitud = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=-90,
        max_value=90,
    )
    longitud = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=-180,
        max_value=180,
    )
    velocidad_kmh = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=0,
        required=False,
        allow_null=True,
    )
    rumbo = serializers.IntegerField(
        min_value=0,
        max_value=359,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = PosicionGPS
        fields = '__all__'

class AlertaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alerta
        fields = '__all__'

class ViajeSerializer(serializers.ModelSerializer):
    id_origen = serializers.PrimaryKeyRelatedField(
        queryset=Ubicacion.objects.filter(activo=True),
    )
    id_destino = serializers.PrimaryKeyRelatedField(
        queryset=Ubicacion.objects.filter(activo=True),
    )
    distancia_km = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=Decimal('0.01'),
        required=True,
    )
    polyline_ruta = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
    )
    fecha_programada = serializers.DateTimeField(required=True)
    fecha_llegada_est = serializers.DateTimeField(required=True)
    unidad_placa = serializers.CharField(source='id_unidad.placa', read_only=True)
    conductor_nombre = serializers.CharField(source='id_conductor.nombre', read_only=True, allow_null=True)
    origen_nombre = serializers.CharField(source='id_origen.nombre', read_only=True)
    destino_nombre = serializers.CharField(source='id_destino.nombre', read_only=True)
    cliente_nombre = serializers.CharField(source='id_cliente.nombre', read_only=True, allow_null=True)

    estado_texto = serializers.SerializerMethodField()
    total_cargas = serializers.SerializerMethodField()

    class Meta:
        model = Viaje
        fields = [
            'id_viaje', 'correlativo', 'id_unidad', 'id_conductor',
            'id_origen', 'id_destino', 'id_cliente', 'id_estado_viaje',
            'estado_texto', 'distancia_km', 'polyline_ruta', 'fecha_programada', 'fecha_salida',
            'fecha_llegada_est', 'fecha_llegada_real',
            'odometro_salida', 'odometro_llegada',
            'combustible_salida_gal', 'combustible_llegada_gal',
            'precio_galon', 'observaciones', 'creado_en',
            'unidad_placa', 'conductor_nombre', 'origen_nombre',
            'destino_nombre', 'cliente_nombre', 'total_cargas',
            'combustible_inicial_gal', 'combustible_final_gal',
            'galones_consumidos', 'odometro_inicial', 'odometro_final',
            'km_recorridos', 'rendimiento_km_gal', 'costo_combustible',
            'alerta_consumo'
        ]
        read_only_fields = ['creado_en']
        extra_kwargs = {
            'id_conductor': {'required': False, 'allow_null': True}
        }

    def validate(self, attrs):
        fields_de_planificacion = {
            'id_origen',
            'id_destino',
            'distancia_km',
            'polyline_ruta',
            'fecha_programada',
            'fecha_llegada_est',
        }
        planificacion_modificada = (
            self.instance is None
            or not self.partial
            or bool(fields_de_planificacion.intersection(attrs))
        )
        if not planificacion_modificada:
            return attrs

        origen = attrs.get(
            'id_origen',
            getattr(self.instance, 'id_origen', None),
        )
        destino = attrs.get(
            'id_destino',
            getattr(self.instance, 'id_destino', None),
        )
        if origen and destino and origen.pk == destino.pk:
            raise serializers.ValidationError({
                'id_destino': 'El origen y el destino deben ser distintos.',
            })

        fecha_programada = attrs.get(
            'fecha_programada',
            getattr(self.instance, 'fecha_programada', None)
            or getattr(self.instance, 'fecha_salida', None),
        )
        if fecha_programada is None:
            raise serializers.ValidationError({
                'fecha_programada': 'La fecha programada es obligatoria.',
            })

        fecha_llegada_est = attrs.get(
            'fecha_llegada_est',
            getattr(self.instance, 'fecha_llegada_est', None),
        )
        if fecha_llegada_est is None:
            raise serializers.ValidationError({
                'fecha_llegada_est': 'Calcula la llegada estimada con una ruta vial.',
            })
        if fecha_llegada_est < fecha_programada:
            raise serializers.ValidationError({
                'fecha_llegada_est': (
                    'La llegada estimada no puede ser anterior a la salida programada.'
                ),
            })

        distancia_km = attrs.get(
            'distancia_km',
            getattr(self.instance, 'distancia_km', None),
        )
        if distancia_km is None or distancia_km <= 0:
            raise serializers.ValidationError({
                'distancia_km': 'La distancia debe provenir de una ruta vial válida.',
            })

        polyline_ruta = attrs.get(
            'polyline_ruta',
            getattr(self.instance, 'polyline_ruta', None),
        )
        if not polyline_ruta or not polyline_ruta.strip():
            raise serializers.ValidationError({
                'polyline_ruta': 'La geometría de la ruta vial es obligatoria.',
            })
        try:
            _validar_geometria_polyline(polyline_ruta)
        except serializers.ValidationError as error:
            raise serializers.ValidationError({
                'polyline_ruta': error.detail,
            })

        return attrs

    def get_estado_texto(self, obj):
        estados = {1: 'PROGRAMADO', 2: 'EN_CURSO', 3: 'COMPLETADO', 4: 'CANCELADO'}
        return estados.get(obj.id_estado_viaje, 'DESCONOCIDO')

    def get_total_cargas(self, obj):
        # Cuenta las cargas asociadas a este viaje
        from .models import Carga
        return Carga.objects.filter(id_viaje=obj).count()

class ViajeDetalleSerializer(ViajeSerializer):
    """Serializer de viaje que incluye las cargas relacionadas."""
    cargas = CargaSerializer(source='carga_set', many=True, read_only=True)