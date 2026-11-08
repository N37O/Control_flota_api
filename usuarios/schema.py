from drf_spectacular.extensions import OpenApiAuthenticationExtension


class SimpleJWTPasswordFlowScheme(OpenApiAuthenticationExtension):
    target_class = 'rest_framework_simplejwt.authentication.JWTAuthentication'
    name = 'jwtAuth'
    priority = 1

    def get_security_definition(self, auto_schema):
        return {
            'type': 'oauth2',
            'flows': {
                'password': {
                    'tokenUrl': '/api/usuarios/login/',
                    'scopes': {},
                },
            },
        }
