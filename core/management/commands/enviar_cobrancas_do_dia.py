from collections import defaultdict
from calendar import monthrange
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.api.cobrancas.services import cobrancas_do_dia
from core.models import Cliente, ContaPagar, Contrato, MensagemEnviada, Parcela
from core.whatsapp import enviar_whatsapp


def moeda(valor):
    return f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def contas_vencendo_em(data):
    ultimo_dia = monthrange(data.year, data.month)[1]
    return [conta for conta in ContaPagar.objects.filter(ativa=True) if min(conta.dia_vencimento, ultimo_dia) == data.day]


def descricao_parcela(parcela):
    contrato = parcela.contrato
    if parcela.tipo == Parcela.Tipo.JUROS:
        prazo = 'Juros semanais' if contrato.periodicidade == 'semanal' else 'Juros mensais'
    elif parcela.tipo == Parcela.Tipo.QUITACAO:
        prazo = 'Quitação do principal'
    elif parcela.numero and contrato.qtd_parcelas:
        prazo = f'Parcela {parcela.numero}/{contrato.qtd_parcelas}'
    elif parcela.numero:
        prazo = f'Parcela {parcela.numero}'
    else:
        prazo = 'Parcela'

    if contrato.tipo == Contrato.Tipo.VENDA:
        return contrato.produto or 'Produto não informado', prazo

    return contrato.get_tipo_display(), prazo


def linhas_categoria(parcelas, titulo, incluir_data_vencimento=False):
    if not parcelas:
        return []

    total = sum((parcela.valor for parcela in parcelas), Decimal('0'))
    linhas = [f'{titulo} — {len(parcelas)} • {moeda(total)}']
    por_tipo = defaultdict(list)
    for parcela in parcelas:
        chave = 'venda' if parcela.contrato.tipo == Contrato.Tipo.VENDA else 'emprestimo'
        por_tipo[chave].append(parcela)

    modalidades = (
        ('venda', '*VENDAS*'),
        ('emprestimo', '*EMPRÉSTIMOS*'),
    )
    for chave, titulo_modalidade in modalidades:
        itens = por_tipo.get(chave, [])
        if not itens:
            continue
        if linhas[-1] != f'{titulo} — {len(parcelas)} • {moeda(total)}':
            # Duas linhas em branco para separar as modalidades.
            linhas.extend(['', ''])
        linhas.append(titulo_modalidade)
        for indice_item, parcela in enumerate(itens):
            item, prazo = descricao_parcela(parcela)
            linhas.extend([
                f'• *{parcela.contrato.cliente.nome}*',
                f'  {item}',
                f'  {prazo} • {moeda(parcela.valor)}',
            ])
            if incluir_data_vencimento:
                linhas.append(f'  Venceu em {parcela.data_vencimento:%d/%m/%Y}')
            # Uma linha em branco entre itens da mesma modalidade.
            if indice_item < len(itens) - 1:
                linhas.append('')
    return linhas


def montar_resumo(parcelas, contas=None):
    contas = list(contas or [])
    atrasadas = [p for p in parcelas if p.status == Parcela.Status.ATRASADA]
    pendentes = [p for p in parcelas if p.status == Parcela.Status.PENDENTE]
    total = sum((parcela.valor for parcela in parcelas), Decimal('0'))
    hoje = timezone.localdate()

    linhas = [
        '*RESUMO DE COBRANÇAS*',
        f'{hoje:%d/%m/%Y}',
        '',
    ]
    if parcelas:
        linhas.extend(linhas_categoria(atrasadas, '*EM ATRASO*', incluir_data_vencimento=True))
        if atrasadas and pendentes:
            linhas.extend(['', ''])
        linhas.extend(linhas_categoria(pendentes, '*VENCEM HOJE*'))
        linhas.extend(['', '', f'*TOTAL A RECEBER: {moeda(total)}*'])
    else:
        linhas.append('Nenhuma cobrança pendente para hoje.')

    if contas:
        linhas.extend(['', '', '*CONTAS A PAGAR*'])
        for conta in contas:
            linhas.extend([f'• *{conta.descricao}*', f'  Vence hoje (recorrente todo dia {conta.dia_vencimento})'])
    return '\n'.join(linhas)


class Command(BaseCommand):
    help = 'Envia ao proprietário um resumo organizado das cobranças atrasadas e de hoje.'

    def handle(self, *args, **kwargs):
        parcelas = list(cobrancas_do_dia())
        contas = contas_vencendo_em(timezone.localdate())
        if not settings.OWNER_WHATSAPP:
            self.stderr.write('OWNER_WHATSAPP não configurado.')
            return

        enviar_whatsapp(settings.OWNER_WHATSAPP, montar_resumo(parcelas, contas))
        dono, _ = Cliente.objects.get_or_create(
            telefone=settings.OWNER_WHATSAPP,
            defaults={'nome': 'Proprietário'},
        )
        MensagemEnviada.objects.create(cliente=dono, tipo=MensagemEnviada.Tipo.RESUMO)
        self.stdout.write(self.style.SUCCESS(f'Resumo enviado: {len(parcelas)} cobrança(s) e {len(contas)} conta(s).'))
