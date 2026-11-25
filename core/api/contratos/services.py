from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from core.models import Contrato, Parcela

CENTAVOS = Decimal('0.01')
DIAS_SEMANA = {
    Contrato.DiaSemana.SEGUNDA: 0,
    Contrato.DiaSemana.TERCA: 1,
    Contrato.DiaSemana.QUARTA: 2,
    Contrato.DiaSemana.QUINTA: 3,
    Contrato.DiaSemana.SEXTA: 4,
    Contrato.DiaSemana.SABADO: 5,
    Contrato.DiaSemana.DOMINGO: 6,
}


def monetario(valor):
    return Decimal(valor).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def adicionar_meses(data, quantidade):
    mes = data.month - 1 + quantidade
    ano, mes = data.year + mes // 12, mes % 12 + 1
    return date(ano, mes, min(data.day, monthrange(ano, mes)[1]))


def adicionar_periodo(data, quantidade, periodicidade):
    if periodicidade == 'semanal':
        return data + timedelta(weeks=quantidade)
    if periodicidade == 'quinzenal':
        return data + timedelta(days=15 * quantidade)
    return adicionar_meses(data, quantidade)


def proximo_dia_semana(referencia, dia_semana):
    deslocamento = (DIAS_SEMANA[dia_semana] - referencia.weekday()) % 7
    return referencia + timedelta(days=deslocamento)


def proximo_vencimento_recorrente(periodicidade, dia_vencimento=None, dia_semana=None, referencia=None):
    referencia = referencia or date.today()
    if periodicidade == 'semanal':
        return proximo_dia_semana(referencia, dia_semana)
    vencimento = date(referencia.year, referencia.month, min(dia_vencimento, monthrange(referencia.year, referencia.month)[1]))
    if vencimento < referencia:
        mes = referencia.month % 12 + 1
        ano = referencia.year + (1 if referencia.month == 12 else 0)
        vencimento = date(ano, mes, min(dia_vencimento, monthrange(ano, mes)[1]))
    return vencimento


@transaction.atomic
def gerar_parcelas_do_contrato(contrato):
    if contrato.tipo == Contrato.Tipo.JUROS:
        if contrato.data_primeira_parcela and not contrato.parcelas.exists():
            Parcela.objects.create(contrato=contrato, tipo=Parcela.Tipo.JUROS, valor=contrato.valor_juros_mensal, data_vencimento=contrato.data_primeira_parcela)
        return
    if contrato.tipo == Contrato.Tipo.VENDA:
        total = contrato.valor_venda - (contrato.valor_entrada or 0)
    else:
        total = contrato.valor_parcela * contrato.qtd_parcelas if contrato.valor_parcela else contrato.valor_principal * (1 + (contrato.taxa_juros_mensal / 100) * contrato.qtd_parcelas)
    valor_parcela = contrato.valor_parcela or monetario(total / contrato.qtd_parcelas)
    contrato.valor_parcela = valor_parcela
    contrato.save(update_fields=['valor_parcela'])
    for numero in range(1, contrato.qtd_parcelas + 1):
        valor = monetario(total - valor_parcela * (contrato.qtd_parcelas - 1)) if numero == contrato.qtd_parcelas else valor_parcela
        Parcela.objects.create(contrato=contrato, numero=numero, valor=valor, data_vencimento=adicionar_periodo(contrato.data_primeira_parcela, numero - 1, contrato.periodicidade))
