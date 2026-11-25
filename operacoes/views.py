from datetime import date
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response
from core.models import Contrato, Parcela
from .models import Moto, Aluguel, CobrancaAluguel, LoteAnimal, Movimento
from .contrato_pdf import contrato_locacao_pdf
from .serializers import MotoSerializer, AluguelSerializer, CobrancaSerializer, LoteSerializer, MovimentoSerializer


class MotosView(generics.ListCreateAPIView):
    queryset = Moto.objects.order_by('placa')
    serializer_class = MotoSerializer


class AlugueisView(generics.ListCreateAPIView):
    queryset = Aluguel.objects.select_related('moto', 'cliente').prefetch_related('cobrancas').order_by('-inicio', '-id')
    serializer_class = AluguelSerializer


class LotesView(generics.ListCreateAPIView):
    queryset = LoteAnimal.objects.order_by('-id')
    serializer_class = LoteSerializer


class MovimentosView(generics.ListCreateAPIView):
    serializer_class = MovimentoSerializer

    def get_queryset(self):
        qs = Movimento.objects.select_related('moto', 'lote')
        for campo in ('moto', 'lote'):
            if value := self.request.query_params.get(campo):
                if not value.isdigit():
                    raise serializers.ValidationError({campo: 'Informe um identificador válido.'})
                qs = qs.filter(**{campo + '_id': value})
        return qs


@api_view(['POST'])
@transaction.atomic
def receber_aluguel(request, pk):
    cobranca = get_object_or_404(CobrancaAluguel.objects.select_for_update().select_related('aluguel__moto'), pk=pk)
    class PagamentoSerializer(serializers.Serializer):
        data = serializers.DateField()
    serializer = PagamentoSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    pagamento = serializer.validated_data['data']
    if pagamento > date.today():
        raise serializers.ValidationError({'data': 'O pagamento não pode estar no futuro.'})
    if cobranca.pago_em:
        raise serializers.ValidationError('Esta cobrança já foi recebida.')
    cobranca.pago_em = pagamento
    cobranca.save(update_fields=['pago_em'])
    Movimento.objects.create(descricao=f'Aluguel {cobranca.aluguel.moto.placa} · vencimento {cobranca.vencimento}', categoria='aluguel', tipo='entrada', valor=cobranca.valor, data=pagamento, moto=cobranca.aluguel.moto, cobranca=cobranca)
    return Response(CobrancaSerializer(cobranca).data)


@api_view(['GET'])
def contrato_aluguel(request, pk):
    aluguel = get_object_or_404(Aluguel.objects.select_related('moto', 'cliente').prefetch_related('cobrancas'), pk=pk)
    return contrato_locacao_pdf(aluguel)


def total(qs, campo='valor'):
    return qs.aggregate(total=Sum(campo))['total'] or Decimal('0')


@api_view(['GET'])
def financeiro(request):
    class PeriodoSerializer(serializers.Serializer):
        inicio = serializers.DateField(default=lambda: date.today().replace(day=1))
        fim = serializers.DateField(default=date.today)
    periodo = PeriodoSerializer(data=request.query_params)
    periodo.is_valid(raise_exception=True)
    inicio, fim = periodo.validated_data['inicio'], periodo.validated_data['fim']
    if fim < inicio:
        raise serializers.ValidationError('A data final deve ser posterior à inicial.')
    movimentos = Movimento.objects.filter(data__range=(inicio, fim))
    recebimentos = Parcela.objects.filter(status=Parcela.Status.PAGA, data_pagamento__range=(inicio, fim))
    emprestimos = Contrato.objects.filter(origem=Contrato.Origem.NOVO, tipo__in=[Contrato.Tipo.TRADICIONAL, Contrato.Tipo.JUROS], data_inicio__range=(inicio, fim))
    entradas = total(movimentos.filter(tipo='entrada')) + total(recebimentos, 'valor_pago')
    saidas = total(movimentos.filter(tipo='saida')) + total(emprestimos, 'valor_principal')
    lotes = []
    # Resultado acumulado por lote; não depende do filtro de caixa mensal.
    for lote in LoteAnimal.objects.prefetch_related('movimentos').order_by('identificacao'):
        entradas_lote = sum((m.valor for m in lote.movimentos.all() if m.tipo == 'entrada'), Decimal('0'))
        despesas = sum((m.valor for m in lote.movimentos.all() if m.tipo == 'saida'), Decimal('0'))
        lotes.append({'id': lote.pk, 'nome': lote.identificacao, 'receitas': entradas_lote, 'despesas': despesas, 'resultado': entradas_lote - despesas})
    return Response({'inicio': inicio, 'fim': fim, 'entradas': entradas, 'saidas': saidas, 'saldo_periodo': entradas - saidas, 'recebido_emprestimos': total(recebimentos, 'valor_pago'), 'capital_emprestado': total(emprestimos, 'valor_principal'), 'lotes': lotes})
