from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0002_contrato_observacoes')]
    operations = [migrations.AddField(model_name='contrato', name='origem', field=models.CharField(choices=[('novo', 'Novo'), ('importado', 'Importado em andamento')], default='novo', max_length=12))]
