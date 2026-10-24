from decimal import Decimal
from datetime import timedelta
from collections import Counter
from types import SimpleNamespace
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from .serializers import ViajeSerializer
from unidades.models import (
	Conductor, DispositivoGPS, EstadoUnidad, TipoUnidad, Unidad,
)
from usuarios.models import Rol, Usuario
from .models import Movimiento, Ubicacion
from .views import (
	_estado_viaje_id, _tipos_unidad_compatibles, _validar_carga_para_viaje,
	_validar_lectura_combustible, _validar_transicion_viaje,
)


def _encode_polyline(points):
	encoded = []
	previous_latitude = 0
	previous_longitude = 0
	for latitude, longitude in points:
		for coordinate, previous in (
			(latitude, previous_latitude),
			(longitude, previous_longitude),
		):
			delta = round(coordinate * 100000) - previous
			value = ~(delta << 1) if delta < 0 else delta << 1
			while value >= 0x20:
				encoded.append(chr((0x20 | (value & 0x1f)) + 63))
				value >>= 5
			encoded.append(chr(value + 63))
		previous_latitude = round(latitude * 100000)
		previous_longitude = round(longitude * 100000)
	return ''.join(encoded)


class CatalogoDistritosTests(TestCase):
	def test_carga_los_262_distritos_con_departamento_y_coordenadas(self):
		ubicaciones = list(Ubicacion.objects.filter(activo=True))
		conteos_departamento = Counter(
			ubicacion.departamento for ubicacion in ubicaciones
		)

		self.assertEqual(len(ubicaciones), 262)
		self.assertEqual(conteos_departamento, {
			'Ahuachapán': 12,
			'Cabañas': 9,
			'Chalatenango': 33,
			'Cuscatlán': 16,
			'La Libertad': 22,
			'La Paz': 22,
			'La Unión': 18,
			'Morazán': 26,
			'San Miguel': 20,
			'San Salvador': 19,
			'San Vicente': 13,
			'Santa Ana': 13,
			'Sonsonate': 16,
			'Usulután': 23,
		})

		conchagua = next(
			ubicacion for ubicacion in ubicaciones
			if ubicacion.nombre == 'Conchagua'
		)
		usulutan = next(
			ubicacion for ubicacion in ubicaciones
			if ubicacion.nombre == 'Usulután'
		)
		self.assertEqual(conchagua.departamento, 'La Unión')
		self.assertEqual(usulutan.departamento, 'Usulután')
		self.assertNotEqual(conchagua.latitud, 0)
		self.assertNotEqual(usulutan.longitud, 0)


class PlanificacionViajeAPITests(TestCase):
	def setUp(self):
		rol = Rol.objects.create(nombre='OPERADOR')
		usuario = Usuario.objects.create_user(
			usuario='viaje-validacion',
			password='test-password',
			nombre='Operador de viajes',
			correo='viaje-validacion@example.com',
			id_rol=rol,
		)
		self.client = APIClient()
		self.client.force_authenticate(user=usuario)
		self.conductor = Conductor.objects.create(nombre='Conductor de prueba')
		self.unidad = Unidad.objects.create(
			placa='TRIP-001',
			id_tipo_unidad=TipoUnidad.objects.create(nombre='Camión'),
			id_estado_unidad=EstadoUnidad.objects.create(nombre='DISPONIBLE'),
			id_conductor=self.conductor,
			capacidad_ton=Decimal('10.00'),
		)
		self.origen = Ubicacion.objects.create(
			nombre='Origen de prueba',
			departamento='La Unión',
			latitud=Decimal('13.300000'),
			longitud=Decimal('-87.800000'),
		)
		self.destino = Ubicacion.objects.create(
			nombre='Destino de prueba',
			departamento='Usulután',
			latitud=Decimal('13.350000'),
			longitud=Decimal('-88.450000'),
		)
		self.payload = {
			'correlativo': 'V-TRIP-001',
			'id_unidad': self.unidad.pk,
			'id_origen': self.origen.pk,
			'id_destino': self.destino.pk,
			'id_estado_viaje': 1,
			'distancia_km': '72.35',
			'polyline_ruta': _encode_polyline([
				(13.300000, -87.800000),
				(13.350000, -88.450000),
			]),
			'fecha_programada': (timezone.now() + timedelta(days=1)).isoformat(),
			'fecha_llegada_est': (timezone.now() + timedelta(days=1, hours=2)).isoformat(),
		}

	def test_serializer_accepts_a_complete_valid_road_trip_plan(self):
		serializer = ViajeSerializer(data=self.payload)

		self.assertTrue(serializer.is_valid(), serializer.errors)

	def test_create_requires_scheduled_and_estimated_arrival(self):
		for field in ('fecha_programada', 'fecha_llegada_est'):
			with self.subTest(field=field):
				payload = self.payload.copy()
				payload.pop(field)

				response = self.client.post(
					'/api/viajes/viajes/',
					payload,
					format='json',
				)

				self.assertEqual(response.status_code, 400, response.data)
				self.assertIn(field, response.data)

	def test_create_requires_a_valid_road_distance_and_geometry(self):
		for field, value in (
			('distancia_km', '0'),
			('polyline_ruta', 'invalid'),
		):
			with self.subTest(field=field):
				payload = self.payload.copy()
				payload[field] = value

				response = self.client.post(
					'/api/viajes/viajes/',
					payload,
					format='json',
				)

				self.assertEqual(response.status_code, 400, response.data)
				self.assertIn(field, response.data)

	def test_create_rejects_arrival_before_scheduled_departure(self):
		payload = self.payload.copy()
		payload['fecha_llegada_est'] = (
			timezone.now() + timedelta(hours=1)
		).isoformat()

		response = self.client.post(
			'/api/viajes/viajes/',
			payload,
			format='json',
		)

		self.assertEqual(response.status_code, 400, response.data)
		self.assertIn('fecha_llegada_est', response.data)

	def test_create_rejects_inactive_locations(self):
		self.origen.activo = False
		self.origen.save(update_fields=['activo'])

		response = self.client.post(
			'/api/viajes/viajes/',
			self.payload,
			format='json',
		)

		self.assertEqual(response.status_code, 400, response.data)
		self.assertIn('id_origen', response.data)

	def test_create_rejects_same_origin_and_destination(self):
		payload = self.payload.copy()
		payload['id_destino'] = self.origen.pk

		response = self.client.post(
			'/api/viajes/viajes/',
			payload,
			format='json',
		)

		self.assertEqual(response.status_code, 400, response.data)
		self.assertIn('id_destino', response.data)


class MovimientoFechaAutomaticaTests(TestCase):
	def setUp(self):
		rol = Rol.objects.create(nombre='OPERADOR')
		usuario = Usuario.objects.create_user(
			usuario='movimiento-fecha',
			password='test-password',
			nombre='Operador',
			correo='movimiento-fecha@example.com',
			id_rol=rol,
		)
		self.client = APIClient()
		self.client.force_authenticate(user=usuario)
		self.unidad = Unidad.objects.create(
			placa='DATE-001',
			id_tipo_unidad=TipoUnidad.objects.create(nombre='Camión'),
			id_estado_unidad=EstadoUnidad.objects.create(nombre='DISPONIBLE'),
			capacidad_ton=Decimal('10.00'),
		)
		self.ubicacion = Ubicacion.objects.create(
			nombre='Punto de prueba',
			latitud=Decimal('13.692900'),
			longitud=Decimal('-89.218200'),
		)

	def test_movement_uses_server_time_instead_of_submitted_time(self):
		inicio = timezone.now()
		fecha_enviada = inicio + timedelta(days=1)
		response = self.client.post(
			'/api/viajes/movimientos/',
			{
				'id_unidad': self.unidad.pk,
				'id_ubicacion': self.ubicacion.pk,
				'tipo': 'ENTRADA',
				'fecha_hora': fecha_enviada.isoformat(),
			},
			format='json',
		)
		fin = timezone.now()

		self.assertEqual(response.status_code, 201, response.data)
		fecha_guardada = parse_datetime(response.data['fecha_hora'])
		self.assertIsNotNone(fecha_guardada)
		self.assertLess(fecha_guardada, fecha_enviada)
		self.assertGreaterEqual(fecha_guardada, inicio - timedelta(seconds=1))
		self.assertLessEqual(fecha_guardada, fin + timedelta(seconds=1))
		self.assertEqual(
			Movimiento.objects.get(pk=response.data['id_movimiento']).fecha_hora,
			fecha_guardada,
		)


class EstadoViajeParsingTests(TestCase):
	def test_transit_aliases_resolve_to_the_same_status(self):
		self.assertEqual(_estado_viaje_id('EN_CURSO'), 2)
		self.assertEqual(_estado_viaje_id('EN_TRANSITO'), 2)
		self.assertEqual(_estado_viaje_id('2'), 2)

	def test_unknown_status_is_rejected(self):
		with self.assertRaises(ValidationError):
			_estado_viaje_id('ESTADO_INVALIDO')

	def test_only_valid_trip_transitions_are_allowed(self):
		for current, target in ((1, 2), (1, 4), (2, 3), (2, 2)):
			with self.subTest(current=current, target=target):
				_validar_transicion_viaje(current, target)

		for current, target in ((1, 3), (2, 4), (3, 2), (4, 1)):
			with self.subTest(current=current, target=target):
				with self.assertRaises(ValidationError):
					_validar_transicion_viaje(current, target)


class CargaCompatibilidadTests(SimpleTestCase):
	def setUp(self):
		self.unidad = SimpleNamespace(
			id_tipo_unidad_id=3,
			placa='TEST-001',
		)
		self.viaje = SimpleNamespace(
			id_cliente_id=7,
			id_unidad=self.unidad,
		)
		self.tipo_carga = SimpleNamespace(unidades_compatibles='[2, 3]')
		self.carga = SimpleNamespace(
			descripcion='Carga de prueba',
			id_cliente_id=7,
			id_tipo_carga=self.tipo_carga,
		)

	def test_compatibility_ids_support_json_and_delimited_values(self):
		self.assertEqual(_tipos_unidad_compatibles(self.tipo_carga), {'2', '3'})
		self.tipo_carga.unidades_compatibles = '2; 3'
		self.assertEqual(_tipos_unidad_compatibles(self.tipo_carga), {'2', '3'})

	def test_carga_requires_matching_customer_and_compatible_unit(self):
		_validar_carga_para_viaje(self.carga, self.viaje)

		self.tipo_carga.unidades_compatibles = '2'
		with self.assertRaises(ValidationError):
			_validar_carga_para_viaje(self.carga, self.viaje)

		self.tipo_carga.unidades_compatibles = '3'
		self.carga.id_cliente_id = 8
		with self.assertRaises(ValidationError):
			_validar_carga_para_viaje(self.carga, self.viaje)


class LecturaCombustibleTests(SimpleTestCase):
	def setUp(self):
		self.unidad = SimpleNamespace(
			placa='TEST-001',
			capacidad_tanque_gal=Decimal('80.00'),
		)

	def test_accepts_zero_and_capacity_boundary(self):
		_validar_lectura_combustible(self.unidad, Decimal('0.00'))
		_validar_lectura_combustible(self.unidad, Decimal('80.00'))

	def test_rejects_empty_tank_when_starting_a_trip(self):
		with self.assertRaises(ValidationError):
			_validar_lectura_combustible(
				self.unidad,
				Decimal('0.00'),
				exigir_positivo=True,
			)

		_validar_lectura_combustible(
			self.unidad,
			Decimal('0.01'),
			exigir_positivo=True,
		)

	def test_rejects_reading_above_tank_capacity(self):
		with self.assertRaises(ValidationError):
			_validar_lectura_combustible(self.unidad, Decimal('80.01'))

	def test_requires_registered_tank_capacity_and_trip_reading(self):
		self.unidad.capacidad_tanque_gal = None
		with self.assertRaises(ValidationError):
			_validar_lectura_combustible(self.unidad, Decimal('20.00'))

		self.unidad.capacidad_tanque_gal = Decimal('80.00')
		with self.assertRaises(ValidationError):
			_validar_lectura_combustible(self.unidad, None)


class PosicionGPSAPITests(TestCase):
	def setUp(self):
		role = Rol.objects.create(nombre='OPERADOR')
		user = Usuario.objects.create_user(
			usuario='gps-operador',
			password='test-password',
			nombre='Operador GPS',
			correo='gps-operador@example.com',
			id_rol=role,
		)
		self.client = APIClient()
		self.client.force_authenticate(user=user)
		self.device = DispositivoGPS.objects.create(numero_serie='GPS-TEST-001')

	def test_position_endpoint_accepts_valid_coordinates_and_filters_by_device_trip(self):
		payload = {
			'id_dispositivo': self.device.pk,
			'latitud': '13.692900',
			'longitud': '-89.218200',
			'velocidad_kmh': '45.50',
			'rumbo': 180,
			'fecha_hora': timezone.now().isoformat(),
		}

		response = self.client.post(
			'/api/viajes/posiciones-gps/actualizar_posicion/',
			payload,
			format='json',
		)

		self.assertEqual(response.status_code, 201, response.data)
		self.assertEqual(response.data['id_dispositivo'], self.device.pk)

		response = self.client.get(
			f'/api/viajes/posiciones-gps/?id_dispositivo={self.device.pk}'
		)
		self.assertEqual(response.status_code, 200, response.data)
		self.assertEqual(response.data['count'], 1)

	def test_position_endpoint_rejects_coordinates_outside_the_globe(self):
		response = self.client.post(
			'/api/viajes/posiciones-gps/actualizar_posicion/',
			{
				'id_dispositivo': self.device.pk,
				'latitud': '91.000000',
				'longitud': '-89.218200',
				'fecha_hora': timezone.now().isoformat(),
			},
			format='json',
		)

		self.assertEqual(response.status_code, 400, response.data)
		self.assertIn('latitud', response.data)
