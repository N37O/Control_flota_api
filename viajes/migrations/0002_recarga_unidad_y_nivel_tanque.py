from django.db import migrations, models
import django.db.models.deletion


def _referenced_column_type(schema_editor, table, column):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COLUMN_TYPE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
            """,
            [table, column],
        )
        result = cursor.fetchone()
    if result is None:
        raise RuntimeError(f'No se encontró la columna {table}.{column}.')
    return result[0]


def _foreign_key_name(schema_editor, table, column):
    with schema_editor.connection.cursor() as cursor:
        constraints = schema_editor.connection.introspection.get_constraints(
            cursor,
            table,
        )
    for name, details in constraints.items():
        if details['foreign_key'] and details['columns'] == [column]:
            return name
    return None


def ajustar_relaciones_recarga(schema_editor, reversa=False):
    if schema_editor.connection.vendor != 'mysql':
        raise RuntimeError('Esta migración requiere MySQL o MariaDB.')

    quote = schema_editor.quote_name
    table = 'recarga_combustible'

    if reversa:
        unidad_fk = _foreign_key_name(schema_editor, table, 'id_unidad')
        if unidad_fk:
            schema_editor.execute(
                f'ALTER TABLE {quote(table)} DROP FOREIGN KEY {quote(unidad_fk)}'
            )
            schema_editor.execute(
                f'ALTER TABLE {quote(table)} DROP COLUMN {quote("id_unidad")}'
            )

    id_viaje_type = _referenced_column_type(
        schema_editor,
        'viaje',
        'id_viaje',
    )
    viaje_fk = _foreign_key_name(schema_editor, table, 'id_viaje')
    if viaje_fk:
        schema_editor.execute(
            f'ALTER TABLE {quote(table)} DROP FOREIGN KEY {quote(viaje_fk)}'
        )

    nullability = 'NOT NULL' if reversa else 'NULL'
    schema_editor.execute(
        f'ALTER TABLE {quote(table)} MODIFY COLUMN {quote("id_viaje")} '
        f'{id_viaje_type} {nullability}'
    )
    schema_editor.execute(
        f'ALTER TABLE {quote(table)} ADD CONSTRAINT '
        f'{quote("recarga_combustible_id_viaje_fk")} '
        f'FOREIGN KEY ({quote("id_viaje")}) '
        f'REFERENCES {quote("viaje")} ({quote("id_viaje")})'
    )

    if not reversa:
        id_unidad_type = _referenced_column_type(
            schema_editor,
            'unidad',
            'id_unidad',
        )
        schema_editor.execute(
            f'ALTER TABLE {quote(table)} ADD COLUMN {quote("id_unidad")} '
            f'{id_unidad_type} NULL'
        )
        schema_editor.execute(
            f'ALTER TABLE {quote(table)} ADD CONSTRAINT '
            f'{quote("recarga_combustible_id_unidad_fk")} '
            f'FOREIGN KEY ({quote("id_unidad")}) '
            f'REFERENCES {quote("unidad")} ({quote("id_unidad")})'
        )


def migrar_relaciones_recarga(apps, schema_editor):
    ajustar_relaciones_recarga(schema_editor)


def revertir_relaciones_recarga(apps, schema_editor):
    ajustar_relaciones_recarga(schema_editor, reversa=True)


def asociar_unidades_a_recargas(apps, schema_editor):
    RecargaCombustible = apps.get_model('viajes', 'RecargaCombustible')
    for recarga in RecargaCombustible.objects.select_related('id_viaje').all().iterator():
        RecargaCombustible.objects.filter(pk=recarga.pk).update(
            id_unidad_id=recarga.id_viaje.id_unidad_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('unidades', '0004_unidad_combustible_actual_gal_and_more'),
        ('viajes', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    migrar_relaciones_recarga,
                    revertir_relaciones_recarga,
                ),
            ],
            state_operations=[
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
            ],
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
