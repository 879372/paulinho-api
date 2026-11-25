from django.core.management.base import BaseCommand
from core.api.cobrancas.services import gerar_juros_mensais, atualizar_atrasos
class Command(BaseCommand):
    help = 'Gera as parcelas mensais de juros dos contratos ativos.'
    def handle(self, *args, **kwargs):
        gerar_juros_mensais(); atualizar_atrasos(); self.stdout.write(self.style.SUCCESS('Juros mensais atualizados.'))
