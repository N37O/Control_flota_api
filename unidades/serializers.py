from decimal import Decimal

from django.core.validators import RegexValidator
from rest_framework import serializers
from .models import (TipoUnidad, EstadoUnidad, Unidad, DispositivoGPS, 
                     Conductor, AsignacionUnidad, Mantenimiento)

class TipoUnidadSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoUnidad
        fields = '__all__'

class EstadoUnidadSerializer(serializers.ModelSerializer):
    class Meta:
        model = EstadoUnidad
        fields = '__all__'

class DispositivoGPSSerializer(serializers.ModelSerializer):
    class Meta:
        model = DispositivoGPS
        fields = '__all__'

class ConductorSerializer(serializers.ModelSerializer):
    dui = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        validators=[RegexValidator(
            regex=r'^[0-9]{8}-[0-9]$',
            message='El DUI debe tener el formato salvadoreño 00000000-0.'
        )],
    )
    licencia = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        validators=[RegexValidator(
            regex=r'^[0-9]{8}-[0-9]$',
            message='La licencia debe tener el formato 00000000-0.'
        )],
    )
    licencia_imagen_url = serializers.SerializerMethodField()

    def validate_dui(self, value):
        if value and Conductor.objects.filter(dui=value).exclude(pk=getattr(self.instance, 'pk', None)).exists():
            raise serializers.ValidationError('Este DUI ya está registrado con otro conductor.')
        return value

    def validate_licencia(self, value):
        if value and Conductor.objects.filter(licencia=value).exclude(pk=getattr(self.instance, 'pk', None)).exists():
            raise serializers.ValidationError('Esta licencia ya está registrada con otro conductor.')
        return value

    class Meta:
        model = Conductor
        fields = [
            'id_conductor', 'nombre', 'dui', 'licencia', 'tipo_licencia',
            'licencia_imagen', 'telefono', 'activo', 'creado_en', 'licencia_imagen_url'
        ]
        extra_kwargs = {
            'nombre': {'required': True, 'allow_blank': False},
            'dui': {'required': False, 'allow_null': True, 'allow_blank': True},
            'licencia': {'required': False, 'allow_null': True, 'allow_blank': True},
            'tipo_licencia': {'required': False, 'allow_null': True, 'allow_blank': True},
            'licencia_imagen': {'required': False, 'allow_null': True, 'allow_blank': True},
            'telefono': {'required': False, 'allow_null': True, 'allow_blank': True},
            'activo': {'required': False, 'default': True},
            'creado_en': {'read_only': True},
            'licencia_imagen_url': {'read_only': True},
        }

    def get_licencia_imagen_url(self, obj):
        if obj.licencia_imagen:
            request = self.context.get('request')
            if request:
                if obj.licencia_imagen.startswith('http'):
                    return obj.licencia_imagen
                return request.build_absolute_uri('/media/' + obj.licencia_imagen.lstrip('/'))
        return None

class AsignacionUnidadSerializer(serializers.ModelSerializer):
    unidad_placa = serializers.CharField(source='id_unidad.placa', read_only=True)
    conductor_nombre = serializers.CharField(source='id_conductor.nombre', read_only=True)

    class Meta:
        model = AsignacionUnidad
        fields = '__all__'
        read_only_fields = ['unidad_placa', 'conductor_nombre']

class MantenimientoSerializer(serializers.ModelSerializer):
    unidad_placa = serializers.CharField(source='id_unidad.placa', read_only=True)

    class Meta:
        model = Mantenimiento
        fields = '__all__'
        read_only_fields = ['unidad_placa']

class UnidadSerializer(serializers.ModelSerializer):
    capacidad_tanque_gal = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=Decimal('0.01'),
        required=True,
    )
    tipo_nombre = serializers.CharField(source='id_tipo_unidad.nombre', read_only=True, allow_null=True)
    estado_nombre = serializers.CharField(source='id_estado_unidad.nombre', read_only=True, allow_null=True)
    conductor_nombre = serializers.CharField(source='id_conductor.nombre', read_only=True, allow_null=True)
    tiene_viaje_activo = serializers.SerializerMethodField()
    ultima_lectura_combustible_gal = serializers.SerializerMethodField()
    fecha_ultima_lectura_combustible = serializers.SerializerMethodField()

    class Meta:
        model = Unidad
        fields = [
            'id_unidad', 'placa', 'codigo_interno', 'id_tipo_unidad',
            'id_estado_unidad', 'id_conductor', 'capacidad_ton',
            'capacidad_tanque_gal', 'combustible_actual_gal',
            'fecha_combustible_actual', 'activo',
            'tiene_viaje_activo', 'ultima_lectura_combustible_gal',
            'fecha_ultima_lectura_combustible',
            'tipo_nombre', 'estado_nombre', 'conductor_nombre', 'creado_en',
            'odometro_actual'
        ]

        extra_kwargs = {
            'id_conductor': {'allow_null': True, 'required': False}
        }

    def get_ultima_lectura_combustible_gal(self, obj):
        return obj.combustible_actual_gal

    def get_tiene_viaje_activo(self, obj):
        return bool(getattr(obj, 'tiene_viaje_activo', False))

    def get_fecha_ultima_lectura_combustible(self, obj):
        return obj.fecha_combustible_actual

    def update(self, instance, validated_data):
        """Forzar la actualización de id_conductor a NULL si viene así"""
        if 'id_conductor' in self.initial_data:
            raw_value = self.initial_data.get('id_conductor')
            if raw_value is None or str(raw_value).strip() == '' or str(raw_value).strip().lower() == 'null':
                validated_data['id_conductor'] = None

        return super().update(instance, validated_data)