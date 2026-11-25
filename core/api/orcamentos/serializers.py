from decimal import Decimal

from rest_framework import serializers


class ItemOrcamentoSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=['servico', 'produto', 'emprestimo_tradicional', 'emprestimo_somente_juros'])
    descricao = serializers.CharField(max_length=255, required=False, allow_blank=True)
    quantidade = serializers.IntegerField(min_value=1, max_value=999, required=False)
    valor_unitario = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'), required=False)
    garantia = serializers.CharField(max_length=120, required=False, allow_blank=True)
    forma_proposta = serializers.ChoiceField(choices=['avista', 'parcelado'], required=False)
    valor_avista = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'), required=False)
    valor_entrada = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'), required=False)
    valor_emprestado = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'), required=False)
    taxa_juros_mensal = serializers.DecimalField(max_digits=6, decimal_places=3, min_value=Decimal('0'), required=False)
    qtd_parcelas = serializers.IntegerField(min_value=1, max_value=120, required=False)
    valor_parcela = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'), required=False)
    juros_mensal = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'), required=False)
    valor_quitacao = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'), required=False)

    def validate(self, attrs):
        tipo = attrs['tipo']
        obrigatorios = {
            'servico': ['descricao', 'quantidade', 'valor_unitario'],
            'produto': ['descricao', 'quantidade', 'forma_proposta'],
            'emprestimo_tradicional': ['valor_emprestado', 'taxa_juros_mensal', 'qtd_parcelas', 'valor_parcela'],
            'emprestimo_somente_juros': ['valor_emprestado', 'juros_mensal', 'valor_quitacao'],
        }[tipo]
        if tipo == 'produto':
            obrigatorios += ['valor_avista'] if attrs.get('forma_proposta') == 'avista' else ['qtd_parcelas', 'valor_parcela']
        erros = {campo: 'Este campo é obrigatório.' for campo in obrigatorios if attrs.get(campo) in (None, '')}
        if erros:
            raise serializers.ValidationError(erros)
        return attrs


class OrcamentoSerializer(serializers.Serializer):
    cliente_nome = serializers.CharField(max_length=160)
    data_emissao = serializers.DateField()
    validade = serializers.DateField()
    observacoes = serializers.CharField(max_length=1200, required=False, allow_blank=True)
    itens = ItemOrcamentoSerializer(many=True, allow_empty=False, max_length=50)

    def validate(self, attrs):
        if attrs['validade'] < attrs['data_emissao']:
            raise serializers.ValidationError({'validade': 'A validade não pode ser anterior à emissão.'})
        return attrs
