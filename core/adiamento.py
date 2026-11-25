from decimal import Decimal
from hashlib import sha256
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from core.models import Contrato, Parcela
from core.api.contratos.services import adicionar_periodo
from operacoes.models import Aluguel, CobrancaAluguel


def preparar(origem, aluguel=False):
    if aluguel:
        if origem.pago_em or origem.transferida_para_id:
            raise ValidationError('Esta cobrança já foi paga ou transferida.')
        pai = origem.aluguel
        data = origem.vencimento
        destino = pai.cobrancas.filter(pago_em__isnull=True, transferida_para__isnull=True, vencimento__gt=data).order_by('vencimento', 'id').first()
    else:
        if origem.status not in (Parcela.Status.PENDENTE, Parcela.Status.ATRASADA) or origem.tipo == Parcela.Tipo.QUITACAO:
            raise ValidationError('Esta parcela não pode ser transferida.')
        pai = origem.contrato
        if pai.status not in (Contrato.Status.ATIVO, Contrato.Status.ATRASADO):
            raise ValidationError('Este contrato não está aberto.')
        data = origem.data_vencimento
        destino = pai.parcelas.filter(status__in=[Parcela.Status.PENDENTE, Parcela.Status.ATRASADA], data_vencimento__gt=data).exclude(tipo=Parcela.Tipo.QUITACAO).order_by('data_vencimento', 'id').first()
    vencimento = (destino.vencimento if aluguel else destino.data_vencimento) if destino else adicionar_periodo(data, 1, pai.periodicidade)
    base = destino.valor if destino else (pai.valor_juros_mensal or Decimal('0')) if not aluguel and pai.tipo == Contrato.Tipo.JUROS else Decimal('0')
    total = base + origem.valor
    if origem.valor <= 0 or total > Decimal('9999999999.99'):
        raise ValidationError('O valor não pode ser transferido: confira o limite da cobrança.')
    versao = sha256(f'{origem.pk}|{origem.valor}|{data}|{destino.pk if destino else 0}|{base}|{vencimento}'.encode()).hexdigest()
    return destino, {'valor_transferido': str(origem.valor), 'valor_proxima': str(base), 'valor_total': str(total), 'vencimento': vencimento.isoformat(), 'nova_cobranca': destino is None, 'versao': versao}


def executar(request, pk, aluguel=False):
    modelo = CobrancaAluguel if aluguel else Parcela
    pai_campo = 'aluguel' if aluguel else 'contrato'
    fonte = get_object_or_404(modelo, pk=pk)
    # O mesmo bloqueio do contrato é usado na baixa para serializar alterações financeiras.
    pai_modelo = Aluguel if aluguel else Contrato
    with transaction.atomic():
        get_object_or_404(pai_modelo.objects.select_for_update(), pk=getattr(fonte, pai_campo+'_id'))
        fonte = modelo.objects.select_for_update().select_related(pai_campo).get(pk=pk)
        destino, dados = preparar(fonte, aluguel)
        if request.method == 'GET':
            return Response(dados)
        if request.data.get('versao') != dados['versao']:
            return Response({'detail': 'A cobrança mudou. Abra novamente a confirmação para conferir os valores.'}, status=409)
        if destino is None:
            if aluguel:
                destino = CobrancaAluguel.objects.create(aluguel=fonte.aluguel, vencimento=dados['vencimento'], valor=dados['valor_total'])
            else:
                destino = Parcela.objects.create(contrato=fonte.contrato, tipo=fonte.tipo, numero=None, data_vencimento=dados['vencimento'], valor=dados['valor_total'])
        else:
            destino.valor = Decimal(dados['valor_total'])
            destino.save(update_fields=['valor'])
        fonte.transferida_para = destino
        campos = ['transferida_para']
        if not aluguel:
            fonte.status = Parcela.Status.TRANSFERIDA
            campos.append('status')
        fonte.save(update_fields=campos)
        if not aluguel:
            contrato = fonte.contrato
            atrasado = contrato.parcelas.filter(status__in=[Parcela.Status.PENDENTE, Parcela.Status.ATRASADA], data_vencimento__lt=timezone.localdate()).exists()
            contrato.status = Contrato.Status.ATRASADO if atrasado else Contrato.Status.ATIVO
            contrato.save(update_fields=['status'])
        return Response({**dados, 'destino': destino.pk})


@api_view(['GET', 'POST'])
def adiar_parcela(request, pk):
    return executar(request, pk)


@api_view(['GET', 'POST'])
def adiar_aluguel(request, pk):
    return executar(request, pk, aluguel=True)
