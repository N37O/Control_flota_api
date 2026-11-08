from rest_framework import viewsets, status, permissions
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from .models import Rol, Usuario
from .permissions import FleetRolePermission, IsAdminRole
from .serializers import (
    RolSerializer,
    UsuarioSerializer,
    LoginSerializer,
    LoginResponseSerializer,
)
from drf_spectacular.utils import extend_schema

@extend_schema(tags=["Usuarios"])
class RolViewSet(viewsets.ModelViewSet):
    queryset = Rol.objects.all()
    serializer_class = RolSerializer
    permission_classes = [IsAdminRole]

    def perform_destroy(self, instance):
        if instance.nombre.strip().upper() in {'ADMINISTRADOR', 'OPERADOR', 'SUPERVISOR'}:
            raise ValidationError({
                'detail': 'No se pueden eliminar los roles base del sistema.'
            })
        if instance.usuario_set.exists():
            raise ValidationError({
                'detail': 'No se puede eliminar este rol porque tiene usuarios asignados.'
            })
        instance.delete()


@extend_schema(tags=["Usuarios"])
class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all()
    serializer_class = UsuarioSerializer

    def get_permissions(self):
        if self.action == 'yo':
            return [IsAuthenticated()]
        return [IsAdminRole()]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.id_rol.nombre.strip().upper() == 'ADMINISTRADOR':
            return queryset
        return queryset.filter(pk=self.request.user.pk)

    @action(detail=False, methods=['get'])
    def activos(self, request):
        usuarios = self.queryset.filter(activo=True)
        serializer = self.get_serializer(usuarios, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def yo(self, request):
        """Devuelve los datos del usuario autenticado"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


@extend_schema(request=LoginSerializer, responses=LoginResponseSerializer, auth=[])
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    oauth_password_flow = (
        request.content_type == 'application/x-www-form-urlencoded'
        and 'username' in request.data
    )
    login_data = request.data
    if oauth_password_flow:
        login_data = {
            'usuario': request.data.get('username'),
            'password': request.data.get('password'),
        }

    serializer = LoginSerializer(data=login_data)
    serializer.is_valid(raise_exception=True)

    try:
        usuario = Usuario.objects.get(
            usuario=serializer.validated_data['usuario'],
            activo=True
        )

        # ✅ Usar check_password de Django (funciona con set_password)
        if usuario.check_password(serializer.validated_data['password']):
            refresh = RefreshToken.for_user(usuario)
            access = refresh.access_token
            if oauth_password_flow:
                lifetime = settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME']
                return Response({
                    'access_token': str(access),
                    'token_type': 'Bearer',
                    'expires_in': int(lifetime.total_seconds()),
                    'refresh_token': str(refresh),
                    'scope': '',
                })
            return Response({
                'refresh': str(refresh),
                'access': str(access),
                'usuario': UsuarioSerializer(usuario).data
            })
        else:
            return Response(
                {'error': 'Credenciales incorrectas'},
                status=status.HTTP_401_UNAUTHORIZED
            )
    except Usuario.DoesNotExist:
        return Response(
            {'error': 'Credenciales incorrectas'},
            status=status.HTTP_401_UNAUTHORIZED
        )