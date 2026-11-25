from calendar import monthrange
from datetime import date
from django.utils import timezone
from django.db.models import Case, IntegerField, Q, Value, When
from core.models import Contrato, Parcela
from core.api.contratos.services import proximo_dia_semana


def atualizar_atrasos():
    Parcela.objects.filter(status=Parcela.Status.PENDENTE, data_vencimento__lt=timezone.localdate()).update(status=Parcela.Status.ATRASADA)
    Contrato.objects.filter(parcelas__status=Parcela.Status.ATRASADA).exclude(status=Contrato.Status.QUITADO).update(status=Contrato.Status.ATRASADO)


def gerar_juros_mensais(referencia=None):
    referencia = referencia or timezone.localdate()
    contratos = Contrato.objects.filter(tipo=Contrato.Tipo.JUROS, status=Contrato.Status.ATIVO)
    for contrato in contratos:
        if contrato.parcelas.filter(tipo=Parcela.Tipo.JUROS).exists():
            continue
        if contrato.periodicidade == 'semanal':
            vencimento = proximo_dia_semana(referencia, contrato.dia_semana)
        else:
            vencimento = date(referencia.year, referencia.month, min(contrato.dia_vencimento, monthrange(referencia.year, referencia.month)[1]))
        Parcela.objects.create(contrato=contrato, tipo=Parcela.Tipo.JUROS, valor=contrato.valor_juros_mensal, data_vencimento=vencimento)


def cobrancas_do_dia():
    atualizar_atrasos()
    hoje = timezone.localdate()
    return (
        Parcela.objects.select_related('contrato__cliente')
        .filter(
            Q(status=Parcela.Status.ATRASADA)
            | Q(status=Parcela.Status.PENDENTE, data_vencimento=hoje)
        )
        .annotate(
            prioridade=Case(
                When(status=Parcela.Status.ATRASADA, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by('prioridade', 'data_vencimento', 'id')
    )
