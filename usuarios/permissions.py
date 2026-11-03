from rest_framework.permissions import BasePermission, SAFE_METHODS


def _role_name(user):
    return str(
        getattr(getattr(user, 'id_rol', None), 'nombre', '')
    ).strip().upper()


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return _role_name(request.user) == 'ADMINISTRADOR'


class IsAdministratorOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return (
            request.method in SAFE_METHODS
            or _role_name(request.user) == 'ADMINISTRADOR'
        )


class IsOperatorOrAdministratorForCreate(BasePermission):
    operator_write_actions = {'create', 'registrar_salida', 'registrar_entrada'}

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        role = _role_name(user)
        if role == 'ADMINISTRADOR':
            return True
        if request.method in SAFE_METHODS:
            return role in {'OPERADOR', 'SUPERVISOR'}
        return (
            role == 'OPERADOR'
            and getattr(view, 'action', None) in self.operator_write_actions
        )


class FleetRolePermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        role = _role_name(user)
        if role == 'ADMINISTRADOR':
            return True

        if request.method in SAFE_METHODS:
            if role == 'OPERADOR':
                return True
            if role == 'SUPERVISOR':
                action = getattr(view, 'action', None) or request.method.lower()
                return action in getattr(view, 'supervisor_read_actions', ())
            return False

        return (
            role == 'OPERADOR'
            and getattr(view, 'action', None)
            in getattr(view, 'operator_write_actions', ())
        )
