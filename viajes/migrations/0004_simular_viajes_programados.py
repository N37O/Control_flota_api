from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('viajes', '0003_catalogo_distritos_el_salvador'),
    ]

    operations = [
        migrations.AddField(
            model_name='viaje',
            name='es_simulado',
            field=models.BooleanField(default=False),
        ),
    ]
