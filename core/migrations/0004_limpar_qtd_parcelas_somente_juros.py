from django.db import migrations


def limpar_quantidade_de_parcelas(apps, schema_editor):
    Contrato = apps.get_model('core', 'Contrato')
    Contrato.objects.filter(tipo='emprestimo_somente_juros').update(qtd_parcelas=None)


class Migration(migrations.Migration):
    dependencies = [('core', '0003_contrato_origem')]
    operations = [migrations.RunPython(limpar_quantidade_de_parcelas, migrations.RunPython.noop)]
