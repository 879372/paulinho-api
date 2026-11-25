from datetime import date
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response
from core.models import Contrato, Parcela
from core.api.contratos.services import adicionar_periodo
from .serializers import BaixaParcelaSerializer, ParcelaSerializer


class ParcelaListView(generics.ListAPIView):
    serializer_class = ParcelaSerializer

    def get_queryset(self):
        queryset = Parcela.objects.select_related('contrato__cliente').order_by('data_vencimento', 'id')
        if status_value := self.request.query_params.get('status'):
            statuses = [value for value in status_value.split(',') if value in Parcela.Status.values]
            if statuses:
                queryset = queryset.filter(status__in=statuses)
        if tipo := self.request.query_params.get('tipo'):
            queryset = queryset.filter(tipo=tipo)
        if contrato_tipo := self.request.query_params.get('contrato_tipo'):
            queryset = queryset.filter(contrato__tipo=contrato_tipo)
        if cliente_id := self.request.query_params.get('cliente'):
            queryset = queryset.filter(contrato__cliente_id=cliente_id)
        if self.request.query_params.get('vencimento') == 'hoje':
            queryset = queryset.filter(data_vencimento=date.today())
        elif vencimento := self.request.query_params.get('vencimento'):
            queryset = queryset.filter(data_vencimento=vencimento)
        if vencimento_de := self.request.query_params.get('vencimento_de'):
            queryset = queryset.filter(data_vencimento__gte=vencimento_de)
        if vencimento_ate := self.request.query_params.get('vencimento_ate'):
            queryset = queryset.filter(data_vencimento__lte=vencimento_ate)
        if busca := self.request.query_params.get('busca'):
            queryset = queryset.filter(Q(contrato__cliente__nome__icontains=busca) | Q(contrato__produto__icontains=busca))
        return queryset


@api_view(['PATCH'])
def dar_baixa(request, pk):
    parcela = get_object_or_404(Parcela.objects.select_related('contrato'), pk=pk)
    if parcela.status == Parcela.Status.PAGA:
        return Response({'detail': 'Parcela já está paga.'}, status=400)
    serializer = BaixaParcelaSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    dados = serializer.validated_data
    parcela.status = Parcela.Status.PAGA
    parcela.data_pagamento = dados.get('data_pagamento', date.today())
    parcela.forma_pagamento = dados['forma_pagamento']
    parcela.valor_pago = dados['valor_pago']
    parcela.save()
    contrato = parcela.contrato
    if contrato.tipo == Contrato.Tipo.JUROS and parcela.tipo == Parcela.Tipo.JUROS:
        proximo_vencimento = adicionar_periodo(parcela.data_vencimento, 1, contrato.periodicidade)
        Parcela.objects.get_or_create(contrato=contrato, tipo=Parcela.Tipo.JUROS, data_vencimento=proximo_vencimento, defaults={'valor': contrato.valor_juros_mensal})
        if contrato.status != Contrato.Status.ATIVO:
            contrato.status = Contrato.Status.ATIVO
            contrato.save(update_fields=['status'])
    elif not contrato.parcelas.exclude(status=Parcela.Status.PAGA).exists():
        contrato.status = Contrato.Status.QUITADO
        contrato.save(update_fields=['status'])
    return Response(ParcelaSerializer(parcela).data)


@api_view(['PATCH'])
@transaction.atomic
def desfazer_baixa(request, pk):
    parcela = get_object_or_404(Parcela.objects.select_for_update().select_related('contrato'), pk=pk)
    if parcela.status != Parcela.Status.PAGA:
        return Response({'detail': 'Somente uma parcela paga pode ter a baixa desfeita.'}, status=400)
    if parcela.tipo == Parcela.Tipo.QUITACAO:
        return Response({'detail': 'A quitação do contrato não pode ser desfeita por esta opção.'}, status=400)

    parcela.status = Parcela.Status.ATRASADA if parcela.data_vencimento < date.today() else Parcela.Status.PENDENTE
    parcela.data_pagamento = None
    parcela.forma_pagamento = None
    parcela.valor_pago = None
    parcela.save(update_fields=['status', 'data_pagamento', 'forma_pagamento', 'valor_pago'])

    contrato = Contrato.objects.select_for_update().get(pk=parcela.contrato_id)
    if contrato.status not in [Contrato.Status.CANCELADO, Contrato.Status.RENEGOCIADO]:
        contrato.status = (
            Contrato.Status.ATRASADO
            if contrato.parcelas.filter(status=Parcela.Status.ATRASADA).exists()
            else Contrato.Status.ATIVO
        )
        contrato.save(update_fields=['status'])

    return Response(ParcelaSerializer(parcela).data)
