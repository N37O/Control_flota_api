from django.db import migrations, models
import django.db.models.deletion


def asociar_unidades_a_recargas(apps, schema_editor):
    RecargaCombustible = apps.get_model('viajes', 'RecargaCombustible')
    for recarga in RecargaCombustible.objects.select_related('id_viaje').filter(id_viaje__isnull=False).iterator():
        RecargaCombustible.objects.filter(pk=recarga.pk).update(
            id_unidad_id=recarga.id_viaje.id_unidad_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('unidades', '0004_unidad_combustible_actual_gal_and_more'),
        ('viajes', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='recargacombustible',
            name='id_unidad',
            field=models.ForeignKey(
                blank=True,
                db_column='id_unidad',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='unidades.unidad',
            ),
        ),
        migrations.AlterField(
            model_name='recargacombustible',
            name='id_viaje',
            field=models.ForeignKey(
                blank=True,
                db_column='id_viaje',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='viajes.viaje',
            ),
        ),
        migrations.AddField(
            model_name='recargacombustible',
            name='nivel_tanque_gal',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=8,
                null=True,
            ),
        ),
        migrations.RunPython(
            asociar_unidades_a_recargas,
            migrations.RunPython.noop,
        ),
    ]
