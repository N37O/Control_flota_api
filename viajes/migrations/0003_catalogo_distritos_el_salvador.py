import json
from pathlib import Path

from django.db import migrations


def cargar_ubicaciones_distritos(apps, schema_editor):
    Ubicacion = apps.get_model('viajes', 'Ubicacion')
    ubicaciones = Ubicacion.objects.using(schema_editor.connection.alias)
    catalogo_path = (
        Path(__file__).resolve().parent.parent
        / 'data'
        / 'ubicaciones_distritos_sv.json'
    )

    with catalogo_path.open(encoding='utf-8') as catalogo_file:
        registros = json.load(catalogo_file)['ubicaciones']

    for registro in registros:
        ubicaciones.get_or_create(
            nombre=registro['nombre'],
            departamento=registro['departamento'],
            defaults={
                'direccion': '',
                'latitud': registro['latitud'],
                'longitud': registro['longitud'],
                'es_base': False,
                'activo': True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('viajes', '0002_recarga_unidad_y_nivel_tanque'),
    ]

    operations = [
        migrations.RunPython(
            cargar_ubicaciones_distritos,
            migrations.RunPython.noop,
        ),
    ]
