from rest_framework import viewsets, status, permissions
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Rol, Usuario
from .serializers import RolSerializer, UsuarioSerializer, LoginSerializer

class RolViewSet(viewsets.ModelViewSet):
    queryset = Rol.objects.all()
    serializer_class = RolSerializer
    # Cambiamos temporalmente a AllowAny para descartar errores de token
    permission_classes = [permissions.AllowAny] 

    def perform_destroy(self, instance):
        if instance.usuario_set.exists():
            raise ValidationError({
                'detail': 'No se puede eliminar este rol porque tiene usuarios asignados.'
            })
        instance.delete()


class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all()
    serializer_class = UsuarioSerializer
    permission_classes = [permissions.IsAuthenticated]

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


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        usuario = Usuario.objects.get(
            usuario=serializer.validated_data['usuario'],
            activo=True
        )

        # ✅ Usar check_password de Django (funciona con set_password)
        if usuario.check_password(serializer.validated_data['password']):
            refresh = RefreshToken.for_user(usuario)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
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