from django.db import models
from unidades.models import Unidad, Conductor

class Ubicacion(models.Model):
    id_ubicacion = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    departamento = models.CharField(max_length=50, blank=True)
    direccion = models.CharField(max_length=200, blank=True)
    latitud = models.DecimalField(max_digits=9, decimal_places=6)
    longitud = models.DecimalField(max_digits=9, decimal_places=6)
    es_base = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'ubicacion'
        unique_together = ('nombre', 'departamento')

    def __str__(self):
        return f"{self.nombre}, {self.departamento}"

class Cliente(models.Model):
    id_cliente = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=150)
    nombre_comercial = models.CharField(max_length=150, blank=True, null=True)
    tipo_cliente = models.CharField(max_length=20, blank=True, null=True)  # Nuevo
    documento = models.CharField(max_length=30, blank=True, null=True)     # Nuevo
    nit = models.CharField(max_length=50, blank=True, null=True)
    contacto = models.CharField(max_length=100, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    correo = models.CharField(max_length=100, blank=True, null=True)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    activo = models.BooleanField(default=True)
    class Meta:
        db_table = 'cliente'

    def __str__(self):
        return self.nombre

class TipoCarga(models.Model):
    id_tipo_carga = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    unidades_compatibles = models.CharField(max_length=100, blank=True, null=True)  # IDs de tipos de unidad compatibles

    class Meta:
        db_table = 'tipo_carga'

    def __str__(self):
        return self.nombre

class EstadoViaje(models.Model):
    id_estado_viaje = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=40)

    class Meta:
        db_table = 'estado_viaje'

    def __str__(self):
        return self.nombre

class Viaje(models.Model):
    id_viaje = models.AutoField(primary_key=True)
    correlativo = models.CharField(max_length=20, unique=True)
    id_unidad = models.ForeignKey('unidades.Unidad', on_delete=models.CASCADE, db_column='id_unidad')
    id_conductor = models.ForeignKey('unidades.Conductor', on_delete=models.CASCADE, db_column='id_conductor')
    id_origen = models.ForeignKey(Ubicacion, on_delete=models.CASCADE, db_column='id_origen', related_name='origen_viajes')
    id_destino = models.ForeignKey(Ubicacion, on_delete=models.CASCADE, db_column='id_destino', related_name='destino_viajes')
    id_cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, db_column='id_cliente')
    id_estado_viaje = models.IntegerField(db_column='id_estado_viaje', default=1)  # 1=Programado, 2=En Curso, 3=Completado, 4=Cancelado
    distancia_km = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    polyline_ruta = models.TextField(blank=True, null=True)
    fecha_programada = models.DateTimeField(blank=True, null=True)
    fecha_salida = models.DateTimeField(blank=True, null=True)
    fecha_llegada_est = models.DateTimeField(blank=True, null=True)
    fecha_llegada_real = models.DateTimeField(blank=True, null=True)
    odometro_salida = models.IntegerField(blank=True, null=True)
    odometro_llegada = models.IntegerField(blank=True, null=True)
    combustible_salida_gal = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    combustible_llegada_gal = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    combustible_inicial_gal = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    combustible_final_gal = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    galones_consumidos = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    odometro_inicial = models.IntegerField(blank=True, null=True)
    odometro_final = models.IntegerField(blank=True, null=True)
    km_recorridos = models.IntegerField(blank=True, null=True)
    rendimiento_km_gal = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    costo_combustible = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    alerta_consumo = models.BooleanField(default=False)
    precio_galon = models.DecimalField(max_digits=6, decimal_places=3, blank=True, null=True)
    observaciones = models.CharField(max_length=255, blank=True, null=True)
    # Campo agregado desde base.txt
    id_usuario_registro = models.IntegerField(blank=True, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'viaje'

    def __str__(self):
        return self.correlativo

class Carga(models.Model):
    id_carga = models.AutoField(primary_key=True)
    id_viaje = models.ForeignKey(Viaje, on_delete=models.SET_NULL, null=True, blank=True, db_column='id_viaje', related_name='cargas')
    id_tipo_carga = models.ForeignKey(TipoCarga, on_delete=models.SET_NULL, null=True, blank=True, db_column='id_tipo_carga')
    id_cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, db_column='id_cliente')
    descripcion = models.CharField(max_length=200, blank=True, null=True)
    cantidad = models.IntegerField(blank=True, null=True)
    unidad_medida = models.CharField(max_length=20, blank=True, null=True)
    peso_ton = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    documento_ref = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'carga'

    def __str__(self):
        return f"{self.descripcion} - {self.peso_ton} ton"

class Movimiento(models.Model):
    # Cambiado a BigAutoField porque en la BD es BIGINT UNSIGNED
    id_movimiento = models.BigAutoField(primary_key=True)
    id_viaje = models.ForeignKey(Viaje, on_delete=models.CASCADE, null=True, blank=True, db_column='id_viaje')
    id_unidad = models.ForeignKey(Unidad, on_delete=models.CASCADE, db_column='id_unidad')
    id_conductor = models.ForeignKey(Conductor, on_delete=models.CASCADE, null=True, blank=True, db_column='id_conductor')
    id_ubicacion = models.ForeignKey(Ubicacion, on_delete=models.CASCADE, db_column='id_ubicacion')
    tipo = models.CharField(max_length=10, choices=[('SALIDA', 'Salida'), ('ENTRADA', 'Entrada')])
    fecha_hora = models.DateTimeField()
    combustible_gal = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    odometro_km = models.IntegerField(null=True, blank=True)
    # Campo agregado desde base.txt
    id_usuario_registro = models.ForeignKey('usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True, db_column='id_usuario_registro')
    observacion = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'movimiento'

class PrecioCombustible(models.Model):
    id_precio = models.AutoField(primary_key=True)
    tipo = models.CharField(max_length=20, default='DIESEL')
    precio_galon = models.DecimalField(max_digits=6, decimal_places=3)
    vigente_desde = models.DateField()
    vigente_hasta = models.DateField(blank=True, null=True)

    class Meta:
        db_table = 'precio_combustible'

    def __str__(self):
        return f"{self.tipo} - ${self.precio_galon}"


class RecargaCombustible(models.Model):
    id_recarga = models.AutoField(primary_key=True)
    id_viaje = models.ForeignKey(
        Viaje,
        on_delete=models.CASCADE,
        db_column='id_viaje',
        blank=True,
        null=True,
    )
    id_unidad = models.ForeignKey(
        Unidad,
        on_delete=models.CASCADE,
        db_column='id_unidad',
        blank=True,
        null=True,
    )
    fecha_hora = models.DateTimeField()
    galones = models.DecimalField(max_digits=6, decimal_places=2)
    nivel_tanque_gal = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
    )
    precio_galon = models.DecimalField(max_digits=6, decimal_places=3)
    lugar = models.CharField(max_length=100, blank=True)
    numero_factura = models.CharField(max_length=40, blank=True)

    class Meta:
        db_table = 'recarga_combustible'

class PosicionGPS(models.Model):
    # Cambiado a BigAutoField porque en la BD es BIGINT UNSIGNED
    id_posicion = models.BigAutoField(primary_key=True)
    id_dispositivo = models.ForeignKey('unidades.DispositivoGPS', on_delete=models.CASCADE, db_column='id_dispositivo')
    id_viaje = models.ForeignKey(Viaje, on_delete=models.CASCADE, null=True, blank=True, db_column='id_viaje')
    latitud = models.DecimalField(max_digits=9, decimal_places=6)
    longitud = models.DecimalField(max_digits=9, decimal_places=6)
    velocidad_kmh = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    rumbo = models.SmallIntegerField(null=True, blank=True)
    fecha_hora = models.DateTimeField()
    recibido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'posicion_gps'

class Alerta(models.Model):
    # Cambiado a BigAutoField porque en la BD es BIGINT UNSIGNED
    id_alerta = models.BigAutoField(primary_key=True)
    id_viaje = models.ForeignKey(Viaje, on_delete=models.CASCADE, null=True, blank=True, db_column='id_viaje')
    id_unidad = models.ForeignKey(Unidad, on_delete=models.CASCADE, null=True, blank=True, db_column='id_unidad')
    tipo = models.CharField(max_length=30)
    mensaje = models.CharField(max_length=255)
    # CORREGIDO: max_length=11 para que quepa 'ADVERTENCIA'
    severidad = models.CharField(max_length=11, choices=[('INFO', 'Info'), ('ADVERTENCIA', 'Advertencia'), ('CRITICA', 'Crítica')], default='ADVERTENCIA')
    fecha = models.DateTimeField(auto_now_add=True)
    atendida = models.BooleanField(default=False)
    # Campo agregado desde base.txt
    atendida_por = models.ForeignKey('usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True, db_column='atendida_por')

    class Meta:
        db_table = 'alerta'