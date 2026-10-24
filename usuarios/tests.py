from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Rol, Usuario


class RolDeletionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.rol = Rol.objects.create(nombre='OPERADOR')

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


class UsuarioDeletionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.rol = Rol.objects.create(nombre='OPERADOR')
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
