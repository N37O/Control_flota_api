from datetime import timedelta
from decimal import Decimal
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.test import APIClient

from unidades.models import Conductor, EstadoUnidad, TipoUnidad, Unidad
from unidades.serializers import UnidadSerializer
from usuarios.models import Rol, Usuario
from viajes.models import Movimiento, Ubicacion
from unidades.views import UnidadViewSet


class UnidadSerializerTests(SimpleTestCase):
    def test_tank_capacity_is_required_and_positive(self):
        field = UnidadSerializer().fields['capacidad_tanque_gal']

        self.assertTrue(field.required)
        self.assertEqual(field.min_value, Decimal('0.01'))
        self.assertEqual(field.run_validation('80.00'), Decimal('80.00'))
        with self.assertRaises(serializers.ValidationError):
            field.run_validation('0.00')

    def test_unit_queryset_marks_programmed_or_in_progress_trips_as_active(self):
        sql, _ = UnidadViewSet.queryset.query.sql_with_params()

        self.assertIn('EXISTS', sql.upper())
        self.assertIn('id_estado_viaje', sql)
        self.assertIn('id_unidad', sql)


class UnidadCombustibleActualTests(TestCase):
    def setUp(self):
        role = Rol.objects.create(nombre='OPERADOR')
        user = Usuario.objects.create_user(
            usuario='unidad-combustible',
            password='test-password',
            nombre='Operador',
            correo='unidad-combustible@example.com',
            id_rol=role,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=user)
        self.unidad = Unidad.objects.create(
            placa='FUEL-001',
            id_tipo_unidad=TipoUnidad.objects.create(nombre='Camión'),
            id_estado_unidad=EstadoUnidad.objects.create(nombre='DISPONIBLE'),
            capacidad_ton=Decimal('10.00'),
            capacidad_tanque_gal=Decimal('80.00'),
        )
        self.conductor = Conductor.objects.create(nombre='Conductor de prueba')
        self.unidad.id_conductor = self.conductor
        self.unidad.save(update_fields=['id_conductor'])
        self.ubicacion = Ubicacion.objects.create(
            nombre='Base de prueba',
            latitud=Decimal('13.692900'),
            longitud=Decimal('-89.218200'),
        )

    def test_unit_api_returns_latest_nonempty_fuel_reading_and_time(self):
        now = timezone.now()
        self.unidad.combustible_actual_gal = Decimal('42.50')
        self.unidad.fecha_combustible_actual = now
        self.unidad.save(update_fields=[
            'combustible_actual_gal',
            'fecha_combustible_actual',
        ])
        Movimiento.objects.create(
            id_unidad=self.unidad,
            id_ubicacion=self.ubicacion,
            tipo='SALIDA',
            fecha_hora=now - timedelta(minutes=1),
            combustible_gal=Decimal('50.00'),
        )

        response = self.client.get('/api/unidades/unidades/')

        self.assertEqual(response.status_code, 200, response.data)
        unidad = response.data['results'][0]
        self.assertFalse(unidad['tiene_viaje_activo'])
        self.assertEqual(unidad['ultima_lectura_combustible_gal'], Decimal('42.50'))
        self.assertEqual(unidad['fecha_ultima_lectura_combustible'], now)

    def test_refuel_without_trip_updates_current_unit_fuel(self):
        now = timezone.now()
        response = self.client.post(
            '/api/viajes/recargas/',
            {
                'id_unidad': self.unidad.pk,
                'fecha_hora': now.isoformat(),
                'galones': '20.00',
                'nivel_tanque_gal': '35.50',
                'precio_galon': '4.250',
                'lugar': 'Gasolinera de prueba',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.combustible_actual_gal, Decimal('35.50'))
        self.assertEqual(self.unidad.fecha_combustible_actual, now)
        self.assertIsNone(response.data['id_viaje'])
        self.assertEqual(response.data['unidad_placa'], self.unidad.placa)

    def test_refuel_rejects_post_fill_level_over_tank_capacity(self):
        response = self.client.post(
            '/api/viajes/recargas/',
            {
                'id_unidad': self.unidad.pk,
                'fecha_hora': timezone.now().isoformat(),
                'galones': '20.00',
                'nivel_tanque_gal': '80.01',
                'precio_galon': '4.250',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('nivel_tanque_gal', response.data)
        self.unidad.refresh_from_db()
        self.assertIsNone(self.unidad.combustible_actual_gal)

class ConductorUploadTests(TestCase):
    def setUp(self):
        self.rol = Rol.objects.create(nombre='ADMINISTRADOR', descripcion='Admin')
        self.user = Usuario.objects.create_user(
            usuario='admin',
            password='admin123',
            nombre='Admin',
            correo='admin@example.com',
            id_rol=self.rol,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_conductor_with_license_image(self):
        image = SimpleUploadedFile(
            'licencia.png',
            b'fake-image-content',
            content_type='image/png'
        )

        response = self.client.post(
            '/api/unidades/conductores/',
            {
                'nombre': 'Carlos Pérez',
                'dui': '12345678-9',
                'licencia': '12345678-9',
                'telefono': '71234567',
                'licencia_imagen': image,
            },
            format='multipart'
        )

        self.assertEqual(response.status_code, 201, response.data)
        conductor = Conductor.objects.get(nombre='Carlos Pérez')
        self.assertTrue(conductor.licencia_imagen)
        self.assertIn('conductores/licencias/', conductor.licencia_imagen)

    def test_create_conductor_rejects_invalid_dui_and_license_formats(self):
        for field_name in ('dui', 'licencia'):
            with self.subTest(field=field_name):
                response = self.client.post(
                    '/api/unidades/conductores/',
                    {
                        'nombre': 'Carlos Pérez',
                        'dui': '12345678-9',
                        'licencia': '12345678-9',
                        field_name: '1234-ABCD',
                    },
                    format='json'
                )

                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn(field_name, response.data)

    def test_create_conductor_rejects_dui_or_license_already_used(self):
        Conductor.objects.create(
            nombre='Conductor existente',
            dui='12345678-9',
            licencia='87654321-0',
        )

        duplicate_cases = (
            ({'dui': '12345678-9', 'licencia': '11111111-1'}, 'dui'),
            ({'dui': '22222222-2', 'licencia': '87654321-0'}, 'licencia'),
        )
        for fields, expected_error in duplicate_cases:
            with self.subTest(field=expected_error):
                response = self.client.post(
                    '/api/unidades/conductores/',
                    {'nombre': 'Nuevo conductor', **fields},
                    format='json'
                )

                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn(expected_error, response.data)

    def test_patch_conductor_with_json_toggle_and_license_image(self):
        conductor = Conductor.objects.create(
            nombre='Carlos Pérez',
            dui='12345678-9',
            licencia='12345678-9',
            tipo_licencia='Pesado',
            telefono='71234567',
        )
        url = f'/api/unidades/conductores/{conductor.id_conductor}/'

        response = self.client.patch(
            url,
            {'nombre': 'Carlos Pérez Actualizado', 'dui': '12345678-9'},
            format='json'
        )
        self.assertEqual(response.status_code, 200, response.data)

        response = self.client.patch(url, {'activo': False}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

        image = SimpleUploadedFile(
            'licencia.png',
            b'fake-image-content',
            content_type='image/png'
        )
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.patch(
                    url,
                    {
                        'nombre': 'Carlos Pérez Actualizado',
                        'dui': '12345678-9',
                        'licencia': '12345678-9',
                        'tipo_licencia': 'Pesado',
                        'telefono': '71234567',
                        'licencia_imagen': image,
                    },
                    format='multipart'
                )

        self.assertEqual(response.status_code, 200, response.data)

    @patch('panel.views.APIClient')
    def test_toggle_conductor_form_action_calls_api(self, mock_api_cls):
        mock_client = mock_api_cls.return_value
        mock_client.get_conductores.return_value = ({'results': []}, None)
        mock_client.toggle_conductor_activo.return_value = ({'status': 'success'}, None)

        session = self.client.session
        session['access_token'] = 'token-test'
        session['user_data'] = {'rol_nombre': 'ADMINISTRADOR'}
        session.save()

        response = self.client.post(
            reverse('panel:conductores'),
            {'action': 'toggle_activo', 'id_conductor': '7', 'nuevo_estado': 'false'}
        )

        self.assertEqual(response.status_code, 302)
        mock_client.toggle_conductor_activo.assert_called_once_with('7', False)
