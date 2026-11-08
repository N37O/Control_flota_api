from urllib.parse import urlencode

from django.test import TestCase
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework_simplejwt.tokens import RefreshToken
from types import SimpleNamespace

from .models import Rol, Usuario
from .permissions import IsOperatorOrAdministratorForCreate
from viajes.views import CargaViewSet, MovimientoViewSet


class RolDeletionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.rol = Rol.objects.create(nombre='ROL_PRUEBA')
        admin_role = Rol.objects.get(nombre='ADMINISTRADOR')
        admin = Usuario.objects.create_user(
            usuario='admin-roles',
            password='test-password',
            nombre='Administrador',
            correo='admin-roles@example.com',
            id_rol=admin_role,
        )
        self.client.force_authenticate(user=admin)

    def test_cannot_delete_role_assigned_to_users(self):
        usuario = Usuario.objects.create_user(
            usuario='operador-prueba',
            password='test-password',
            nombre='Operador de prueba',
            correo='operador-prueba@example.com',
            id_rol=self.rol,
        )

        response = self.client.delete(f'/api/usuarios/roles/{self.rol.pk}/')

        self.assertEqual(response.status_code, 400)
        self.assertIn('usuarios asignados', str(response.data).lower())
        self.assertTrue(Rol.objects.filter(pk=self.rol.pk).exists())
        self.assertTrue(Usuario.objects.filter(pk=usuario.pk).exists())

    def test_can_delete_role_without_users(self):
        response = self.client.delete(f'/api/usuarios/roles/{self.rol.pk}/')

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Rol.objects.filter(pk=self.rol.pk).exists())


class ProductionSuperuserTests(TestCase):
    def test_createsuperuser_assigns_the_administrator_role(self):
        user = Usuario.objects.create_superuser(
            usuario='deployment-admin',
            password='test-password',
            nombre='Administrador de despliegue',
            correo='deployment-admin@example.com',
        )

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertEqual(user.id_rol.nombre, 'ADMINISTRADOR')


class StandardRolePermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.roles = {
            name: Rol.objects.get(nombre=name)
            for name in ('ADMINISTRADOR', 'OPERADOR', 'SUPERVISOR')
        }

    def _login_as(self, role_name):
        user = Usuario.objects.create_user(
            usuario=f'roles-{role_name.lower()}',
            password='test-password',
            nombre=role_name.title(),
            correo=f'roles-{role_name.lower()}@example.com',
            id_rol=self.roles[role_name],
        )
        self.client.force_authenticate(user=user)
        return user

    def test_only_administrator_can_create_roles(self):
        for role_name in ('OPERADOR', 'SUPERVISOR'):
            self._login_as(role_name)
            response = self.client.post(
                '/api/usuarios/roles/',
                {'nombre': 'ROL_PRUEBA'},
                format='json',
            )
            self.assertEqual(response.status_code, 403)
            self.client.force_authenticate(user=None)

        self._login_as('ADMINISTRADOR')
        response = self.client.post(
            '/api/usuarios/roles/',
            {'nombre': 'ROL_PRUEBA'},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_operator_can_create_operational_records(self):
        self._login_as('OPERADOR')
        location_response = self.client.post(
            '/api/viajes/ubicaciones/',
            {
                'nombre': 'Punto de viaje del operador',
                'departamento': 'Mapa',
                'direccion': 'Punto seleccionado en el mapa',
                'latitud': '13.700000',
                'longitud': '-89.200000',
                'activo': True,
            },
            format='json',
        )
        self.assertEqual(location_response.status_code, 201, location_response.data)

        for path in (
            '/api/unidades/unidades/',
            '/api/viajes/viajes/',
            '/api/viajes/ubicaciones/',
            '/api/viajes/movimientos/',
            '/api/viajes/recargas/',
        ):
            with self.subTest(path=path):
                response = self.client.post(path, {}, format='json')
                self.assertNotEqual(response.status_code, 403, response.data)

    def test_operator_can_create_loads_and_movements_but_not_update_them(self):
        user = self._login_as('OPERADOR')
        self.assertIn(
            IsOperatorOrAdministratorForCreate,
            CargaViewSet.permission_classes,
        )
        self.assertIn(
            IsOperatorOrAdministratorForCreate,
            MovimientoViewSet.permission_classes,
        )
        permission = IsOperatorOrAdministratorForCreate()
        for action in ('create', 'registrar_salida', 'registrar_entrada'):
            request = APIRequestFactory().post('/api/viajes/movimientos/', {})
            request.user = user
            self.assertTrue(
                permission.has_permission(request, SimpleNamespace(action=action))
            )
        request = APIRequestFactory().patch('/api/viajes/cargas/1/', {})
        request.user = user
        self.assertFalse(
            permission.has_permission(
                request,
                SimpleNamespace(action='partial_update'),
            )
        )

    def test_supervisor_cannot_create_or_modify_operational_records(self):
        self._login_as('SUPERVISOR')
        for path in (
            '/api/unidades/unidades/',
            '/api/viajes/viajes/',
            '/api/viajes/ubicaciones/',
            '/api/viajes/movimientos/',
            '/api/viajes/recargas/',
        ):
            with self.subTest(path=path):
                response = self.client.post(path, {}, format='json')
                self.assertEqual(response.status_code, 403, response.data)


class UsuarioDeletionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.rol = Rol.objects.get(nombre='ADMINISTRADOR')
        self.request_user = Usuario.objects.create_user(
            usuario='admin-prueba',
            password='test-password',
            nombre='Administrador de prueba',
            correo='admin-prueba@example.com',
            id_rol=self.rol,
        )
        self.target_user = Usuario.objects.create_user(
            usuario='usuario-prueba',
            password='test-password',
            nombre='Usuario de prueba',
            correo='usuario-prueba@example.com',
            id_rol=self.rol,
        )
        self.client.force_authenticate(user=self.request_user)

    def test_can_delete_user(self):
        response = self.client.delete(
            f'/api/usuarios/usuarios/{self.target_user.pk}/'
        )

        self.assertEqual(response.status_code, 204, response.data)
        self.assertFalse(Usuario.objects.filter(pk=self.target_user.pk).exists())


class TokenRefreshTests(TestCase):
    def test_refresh_endpoint_returns_new_access_token(self):
        rol = Rol.objects.create(nombre='REFRESH_TEST')
        usuario = Usuario.objects.create_user(
            usuario='refresh-prueba',
            password='test-password',
            nombre='Usuario refresh',
            correo='refresh-prueba@example.com',
            id_rol=rol,
        )
        refresh_token = str(RefreshToken.for_user(usuario))

        response = APIClient().post(
            '/api/usuarios/token/refresh/',
            {'refresh': refresh_token},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)


class SwaggerOAuthAuthorizationTests(TestCase):
    def setUp(self):
        self.rol = Rol.objects.get(nombre='ADMINISTRADOR')
        self.usuario = Usuario.objects.create_user(
            usuario='swagger-prueba',
            password='test-password',
            nombre='Usuario Swagger',
            correo='swagger-prueba@example.com',
            id_rol=self.rol,
        )

    def test_swagger_login_form_returns_access_token_accepted_by_api(self):
        response = APIClient().generic(
            'POST',
            '/api/usuarios/login/',
            urlencode({
                'username': 'swagger-prueba',
                'password': 'test-password',
                'grant_type': 'password',
            }),
            content_type='application/x-www-form-urlencoded',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['token_type'], 'Bearer')
        self.assertEqual(response.data['expires_in'], 8 * 60 * 60)
        self.assertIn('refresh_token', response.data)

        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {response.data['access_token']}"
        )
        protected_response = client.get('/api/usuarios/usuarios/yo/')
        self.assertEqual(protected_response.status_code, 200, protected_response.data)
        self.assertEqual(protected_response.data['usuario'], 'swagger-prueba')

    def test_swagger_ui_and_oauth2_schema_are_public_and_configured(self):
        client = APIClient()

        swagger_response = client.get('/swagger/')
        self.assertEqual(swagger_response.status_code, 200)

        schema_response = client.get('/schema/')
        self.assertEqual(schema_response.status_code, 200)
        auth_scheme = schema_response.data['components']['securitySchemes']['jwtAuth']
        self.assertEqual(auth_scheme['type'], 'oauth2')
        self.assertEqual(
            auth_scheme['flows']['password']['tokenUrl'],
            '/api/usuarios/login/',
        )

    def test_existing_json_login_response_is_unchanged(self):
        response = APIClient().post(
            '/api/usuarios/login/',
            {'usuario': 'swagger-prueba', 'password': 'test-password'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('usuario', response.data)
        self.assertNotIn('password', response.data['usuario'])
        self.assertNotIn('is_staff', response.data['usuario'])
