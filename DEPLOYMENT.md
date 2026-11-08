# Despliegue en Linux con MySQL y Nginx

La aplicación debe servirse detrás de HTTPS y un proxy inverso. No uses
`manage.py runserver` en producción, no publiques MySQL en Internet y no sirvas
`media/` como directorio público: puede contener imágenes de licencias.

## 1. Preparar el servidor

Instala Python 3.11 o superior, MySQL y Nginx. Crea un usuario de sistema sin
privilegios para ejecutar la API y una base de datos con un usuario MySQL propio
de la aplicación. Limita la conexión MySQL a localhost o a la red privada.

Clona el repositorio en `/srv/control-flota-api` y prepara los directorios
persistentes:

```sh
sudo install -d -o control-flota -g control-flota /var/lib/control-flota/media
sudo install -d -o control-flota -g control-flota /var/lib/control-flota/staticfiles
sudo install -d -o root -g control-flota -m 0750 /etc/control-flota
```

Configura `/etc/control-flota/api.env` usando `.env.example` como referencia.
Usa valores aleatorios para `DJANGO_SECRET_KEY` y `DB_PASSWORD`; no los guardes
en Git ni los incluyas en mensajes o registros. Genera la clave de Django con
`python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
y cópiala únicamente al archivo de entorno. `DJANGO_ALLOWED_HOSTS` debe
contener el dominio o IP exactos. Configura los orígenes reales del frontend
solo si se sirve desde otro origen.

El proyecto reportó la IP `158.23.59.41`. Para HTTPS en Nginx configura un
dominio y un certificado TLS válidos; reemplaza `YOUR_DOMAIN` en
`deploy/nginx.conf` y actualiza `DJANGO_ALLOWED_HOSTS` y
`CSRF_TRUSTED_ORIGINS`. Si solo existe HTTP, detén el despliegue hasta activar
HTTPS; la configuración de producción redirige HTTP a HTTPS.
Mantén `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` y
`DJANGO_SECURE_HSTS_PRELOAD` desactivados salvo que controles todos los
subdominios y estés listo para que los navegadores fuercen HTTPS en ellos.

## 2. Instalar y preparar

Con el entorno virtual activado, desde `/srv/control-flota-api`:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
set -a
. /etc/control-flota/api.env
set +a
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
```

Antes de migrar una base de datos existente, haz un respaldo y valida el plan
contra una copia de MySQL. La migración `viajes.0005_align_model_schema` añade
campos que faltan en el historial Django actual; no la ejecutes sobre producción
hasta confirmar que las tablas/columnas no fueron creadas manualmente y que el
contenido de la base se conserva. No marques migraciones como aplicadas para
evitar errores sin haber comparado el esquema.

Después de validar la copia:

```sh
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

El superusuario recibirá automáticamente el rol `ADMINISTRADOR`. Crea usuarios
de prueba con credenciales distintas; la base SQLite del entorno de desarrollo
no se copia a producción.

## 3. Ejecutar Gunicorn

Instala `deploy/control-flota-api.service` como
`/etc/systemd/system/control-flota-api.service` y reemplaza el comando
`ExecStart` con el siguiente ejemplo si prefieres configurarlo manualmente:

```sh
/srv/control-flota-api/.venv/bin/gunicorn flota_api.wsgi:application \
  --bind 127.0.0.1:8000 \
  --workers 3 \
  --access-logfile - \
  --error-logfile -
```

El unit file ya carga `EnvironmentFile=/etc/control-flota/api.env`, ejecuta
como usuario `control-flota` y reinicia ante fallos. Actívalo con
`sudo systemctl daemon-reload && sudo systemctl enable --now control-flota-api`.
Instala `deploy/nginx.conf` en `sites-available`, reemplaza el dominio y habilita
el sitio después de obtener el certificado TLS. No expongas el puerto 8000
públicamente.

Nginx debe terminar TLS, pasar las solicitudes al puerto local y enviar
`Host`, `X-Forwarded-For` y `X-Forwarded-Proto: https`. Sirve únicamente
`/static/` desde el `STATIC_ROOT` configurado. No crees un `alias` público para
`/media/`; las imágenes de licencia se entregan por un endpoint autenticado.

## 4. Comprobación posterior

Prueba el acceso HTTPS, el login JWT, un endpoint permitido y uno denegado para
cada rol. Comprueba también Swagger y que MySQL no acepte conexiones desde
Internet. Revisa `python manage.py check --deploy` y los logs de systemd/Nginx.
