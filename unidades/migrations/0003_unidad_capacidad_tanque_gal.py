from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('unidades', '0002_conductor_licencia_imagen_unidad_odometro_actual_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='unidad',
            name='capacidad_tanque_gal',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=8,
                null=True,
            ),
        ),
    ]
