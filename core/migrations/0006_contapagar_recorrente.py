from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def copiar_dia_e_status(apps, schema_editor):
    ContaPagar = apps.get_model('core', 'ContaPagar')
    for conta in ContaPagar.objects.all():
        conta.dia_vencimento = conta.data_vencimento.day
        conta.ativa = not conta.paga
        conta.encerrada_em = conta.data_pagamento if conta.paga else None
        conta.save(update_fields=['dia_vencimento', 'ativa', 'encerrada_em'])


class Migration(migrations.Migration):
    dependencies = [('core', '0005_contapagar')]

    operations = [
        migrations.AddField(model_name='contapagar', name='dia_vencimento', field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(model_name='contapagar', name='ativa', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='contapagar', name='encerrada_em', field=models.DateField(blank=True, null=True)),
        migrations.RunPython(copiar_dia_e_status, migrations.RunPython.noop),
        migrations.AlterField(model_name='contapagar', name='dia_vencimento', field=models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(31)])),
        migrations.RemoveField(model_name='contapagar', name='data_vencimento'),
        migrations.RemoveField(model_name='contapagar', name='paga'),
        migrations.RemoveField(model_name='contapagar', name='data_pagamento'),
        migrations.AlterModelOptions(name='contapagar', options={'ordering': ['-ativa', 'dia_vencimento', 'descricao']}),
    ]
