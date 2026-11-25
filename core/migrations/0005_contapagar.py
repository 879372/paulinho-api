from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0004_limpar_qtd_parcelas_somente_juros')]

    operations = [
        migrations.CreateModel(
            name='ContaPagar',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('descricao', models.CharField(max_length=255)),
                ('data_vencimento', models.DateField()),
                ('paga', models.BooleanField(default=False)),
                ('data_pagamento', models.DateField(blank=True, null=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['paga', 'data_vencimento', 'descricao']},
        ),
    ]
