from django.utils import timezone
from rest_framework import generics

from core.models import ContaPagar
from .serializers import ContaPagarSerializer, StatusContaSerializer


class ContaPagarListCreateView(generics.ListCreateAPIView):
    queryset = ContaPagar.objects.all()
    serializer_class = ContaPagarSerializer
    pagination_class = None


class ContaPagarDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ContaPagar.objects.all()

    def get_serializer_class(self):
        return StatusContaSerializer if self.request.method == 'PATCH' else ContaPagarSerializer

    def perform_update(self, serializer):
        conta = self.get_object()
        conta.ativa = serializer.validated_data['ativa']
        conta.encerrada_em = None if conta.ativa else timezone.localdate()
        conta.save(update_fields=['ativa', 'encerrada_em'])
