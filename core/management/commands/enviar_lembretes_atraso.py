from datetime import date
from django.core.management.base import BaseCommand
from core.models import Contrato, MensagemEnviada, Parcela
from core.api.cobrancas.services import cobrancas_do_dia
from core.whatsapp import enviar_whatsapp


def moeda(valor):
    return f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def referencia_parcela(parcela):
    contrato = parcela.contrato
    if parcela.tipo == Parcela.Tipo.JUROS:
        prazo = 'Juros semanais' if contrato.periodicidade == 'semanal' else 'Juros mensais'
    elif parcela.tipo == Parcela.Tipo.QUITACAO:
        prazo = 'Quitação do principal'
    elif parcela.numero and contrato.qtd_parcelas:
        prazo = f'Parcela {parcela.numero} de {contrato.qtd_parcelas}'
    elif parcela.numero:
        prazo = f'Parcela {parcela.numero}'
    else:
        prazo = 'Parcela'

    if contrato.tipo == Contrato.Tipo.VENDA:
        return '🛍️ *Produto*', contrato.produto or 'Produto não informado', prazo
    return '💸 *Empréstimo*', contrato.get_tipo_display(), prazo


class Command(BaseCommand):
    help = 'Envia uma única notificação para cada parcela atrasada.'
    def handle(self, *args, **kwargs):
        enviados = 0
        for parcela in cobrancas_do_dia().filter(status=Parcela.Status.ATRASADA):
            if MensagemEnviada.objects.filter(
                parcela=parcela,
                tipo=MensagemEnviada.Tipo.ATRASO,
                enviado_em__date=date.today(),
            ).exists():
                continue
            titulo, descricao, prazo = referencia_parcela(parcela)
            texto = '\n'.join([
                f'Olá, *{parcela.contrato.cliente.nome}*! 👋',
                '',
                '🔔 *LEMBRETE DE PAGAMENTO*',
                titulo + f': {descricao}',
                f'📄 *Referência:* {prazo}',
                f'📅 *Vencimento:* {parcela.data_vencimento:%d/%m/%Y}',
                f'💰 *Valor em aberto:* {moeda(parcela.valor)}',
                '',
                'Identificamos que este pagamento está em atraso. Por favor, entre em contato para regularizar.',
                'Obrigado! 🤝',
            ])
            enviar_whatsapp(parcela.contrato.cliente.telefone, texto)
            MensagemEnviada.objects.create(cliente=parcela.contrato.cliente, parcela=parcela, tipo=MensagemEnviada.Tipo.ATRASO); enviados += 1
        self.stdout.write(self.style.SUCCESS(f'{enviados} lembrete(s) enviado(s).'))
