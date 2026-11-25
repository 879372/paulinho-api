from rest_framework import serializers

from core.models import ContaPagar


class ContaPagarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContaPagar
        fields = ['id', 'descricao', 'dia_vencimento', 'ativa', 'encerrada_em', 'criado_em']
        read_only_fields = ['id', 'ativa', 'encerrada_em', 'criado_em']


class StatusContaSerializer(serializers.Serializer):
    ativa = serializers.BooleanField()
