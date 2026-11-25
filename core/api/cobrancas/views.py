from datetime import date
from django.db.models import Sum
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response
from core.models import Parcela
from core.api.parcelas.serializers import ParcelaSerializer
from .services import cobrancas_do_dia


class CobrancasDoDiaListView(generics.ListAPIView):
    serializer_class = ParcelaSerializer

    def get_queryset(self):
        queryset = cobrancas_do_dia()
        if status_value := self.request.query_params.get('status'):
            queryset = queryset.filter(status=status_value)
        if busca := self.request.query_params.get('busca'):
            queryset = queryset.filter(contrato__cliente__nome__icontains=busca)
        return queryset


@api_view(['GET'])
def dashboard_view(request):
    hoje = date.today()
    parcelas = Parcela.objects.all()
    return Response({
        'a_receber': parcelas.filter(
            data_vencimento__year=hoje.year,
            data_vencimento__month=hoje.month,
            status__in=[Parcela.Status.PENDENTE, Parcela.Status.ATRASADA],
        ).aggregate(total=Sum('valor'))['total'] or 0,
        'recebido_mes': parcelas.filter(status=Parcela.Status.PAGA, data_pagamento__year=hoje.year, data_pagamento__month=hoje.month).aggregate(total=Sum('valor_pago'))['total'] or 0,
        'vencendo_hoje': parcelas.filter(data_vencimento=hoje).exclude(status=Parcela.Status.PAGA).count(),
        'atrasados': parcelas.filter(status=Parcela.Status.ATRASADA).count(),
    })
