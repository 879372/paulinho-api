from rest_framework import generics
from core.models import Cliente
from rest_framework.decorators import api_view
from django.shortcuts import get_object_or_404
from .pdf import relatorio_cliente_pdf
from .serializers import ClienteDetailSerializer, ClienteSerializer


class ClienteListCreateView(generics.ListCreateAPIView):
    serializer_class = ClienteSerializer

    def get_queryset(self):
        queryset = Cliente.objects.all().order_by('-criado_em')
        if busca := self.request.query_params.get('busca'):
            queryset = queryset.filter(nome__icontains=busca)
        if self.request.query_params.get('com_cpf') == 'true':
            queryset = queryset.exclude(cpf__isnull=True).exclude(cpf='')
        return queryset


class ClienteDetailView(generics.RetrieveUpdateAPIView):
    queryset = Cliente.objects.prefetch_related('contratos__parcelas').all()
    serializer_class = ClienteDetailSerializer


@api_view(['GET'])
def relatorio(request, pk):
    cliente = get_object_or_404(Cliente.objects.prefetch_related('contratos__parcelas'), pk=pk)
    return relatorio_cliente_pdf(cliente)
