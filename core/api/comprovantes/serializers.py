from decimal import Decimal

from rest_framework import serializers


class ComprovanteCompraSerializer(serializers.Serializer):
    cliente_nome = serializers.CharField(max_length=160)
    produto = serializers.CharField(max_length=255)
    valor_produto = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    forma_pagamento = serializers.ChoiceField(choices=[
        ('pix', 'PIX'),
        ('dinheiro', 'Dinheiro'),
        ('cartao_credito', 'Cartão de crédito'),
        ('cartao_debito', 'Cartão de débito'),
        ('transferencia', 'Transferência'),
    ])
    data_compra = serializers.DateField()
    garantia = serializers.CharField(max_length=120)
