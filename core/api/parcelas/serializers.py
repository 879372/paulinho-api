from rest_framework import serializers
from core.models import Parcela


class ParcelaSerializer(serializers.ModelSerializer):
    cliente_nome = serializers.CharField(source='contrato.cliente.nome', read_only=True)
    contrato_tipo = serializers.CharField(source='contrato.tipo', read_only=True)
    produto = serializers.CharField(source='contrato.produto', read_only=True)
    contrato_descricao = serializers.SerializerMethodField()

    class Meta:
        model = Parcela
        fields = ['id', 'contrato', 'cliente_nome', 'contrato_tipo', 'produto', 'contrato_descricao', 'tipo', 'numero', 'valor', 'data_vencimento', 'status', 'data_pagamento', 'forma_pagamento', 'valor_pago']
        read_only_fields = ['id', 'contrato', 'status', 'data_pagamento', 'forma_pagamento', 'valor_pago']

    def get_contrato_descricao(self, parcela):
        if parcela.contrato.tipo == 'venda':
            return parcela.contrato.produto or 'Venda parcelada'
        if parcela.contrato.tipo == 'emprestimo_tradicional':
            return 'Empréstimo tradicional'
        return 'Empréstimo • somente juros'


class BaixaParcelaSerializer(serializers.Serializer):
    data_pagamento = serializers.DateField(required=False)
    forma_pagamento = serializers.ChoiceField(choices=Parcela.Forma.choices)
    valor_pago = serializers.DecimalField(max_digits=12, decimal_places=2)

    def validate_valor_pago(self, value):
        if value <= 0:
            raise serializers.ValidationError('O valor pago deve ser positivo.')
        return value
