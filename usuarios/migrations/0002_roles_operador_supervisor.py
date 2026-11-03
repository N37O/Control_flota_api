from django.db import migrations


ROLE_DESCRIPTIONS = {
    'ADMINISTRADOR': (
        'Administra usuarios, roles y la configuración completa del sistema.'
    ),
    'OPERADOR': (
        'Registra unidades, cargas, movimientos, recargas y viajes.'
    ),
    'SUPERVISOR': (
        'Consulta seguimiento, mapas, estados de unidades e informes.'
    ),
}


def create_standard_roles(apps, schema_editor):
    Rol = apps.get_model('usuarios', 'Rol')
    for name, description in ROLE_DESCRIPTIONS.items():
        role, created = Rol.objects.using(schema_editor.connection.alias).get_or_create(
            nombre=name,
            defaults={'descripcion': description},
        )
        if not created and not role.descripcion.strip():
            role.descripcion = description
            role.save(
                update_fields=['descripcion'],
                using=schema_editor.connection.alias,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_standard_roles, migrations.RunPython.noop),
    ]
