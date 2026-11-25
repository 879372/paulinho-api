from datetime import date
from decimal import Decimal
from django.db import transaction
from rest_framework import serializers
from core.models import Contrato, Parcela
from core.api.parcelas.serializers import ParcelaSerializer
from .services import DIAS_SEMANA, gerar_parcelas_do_contrato, monetario, proximo_vencimento_recorrente


class ContratoCreateSerializer(serializers.ModelSerializer):
    qtd_parcelas = serializers.IntegerField(min_value=1, max_value=120, required=False, allow_null=True)
    periodicidade = serializers.ChoiceField(choices=['mensal', 'quinzenal', 'semanal'], default='mensal', required=False)
    calcular_emprestimo_por = serializers.ChoiceField(choices=['taxa', 'valor_parcela'], default='taxa', write_only=True, required=False)
    calcular_por = serializers.ChoiceField(
        choices=['valor_venda', 'valor_parcela'],
        default='valor_venda',
        write_only=True,
        required=False,
    )
    qtd_parcelas_pagas = serializers.IntegerField(min_value=0, required=False, default=0, write_only=True)
    data_ultimo_pagamento = serializers.DateField(required=False, allow_null=True, write_only=True)
    forma_pagamento_historico = serializers.ChoiceField(choices=Parcela.Forma.choices, required=False, write_only=True)

    class Meta:
        model = Contrato
        fields = ['id', 'cliente', 'origem', 'tipo', 'data_inicio', 'produto', 'valor_produto', 'valor_venda', 'teve_entrada', 'valor_entrada', 'valor_principal', 'taxa_juros_mensal', 'valor_juros_mensal', 'qtd_parcelas', 'valor_parcela', 'periodicidade', 'data_primeira_parcela', 'dia_vencimento', 'dia_semana', 'observacoes', 'calcular_por', 'calcular_emprestimo_por', 'qtd_parcelas_pagas', 'data_ultimo_pagamento', 'forma_pagamento_historico']
        read_only_fields = ['id']

    def validate(self, attrs):
        tipo = attrs['tipo']
        if tipo == Contrato.Tipo.JUROS and attrs.get('origem', Contrato.Origem.NOVO) == Contrato.Origem.IMPORTADO:
            raise serializers.ValidationError({'tipo': 'Somente juros está disponível apenas para contratos novos.'})
        obrigatorios = ['produto', 'qtd_parcelas', 'data_primeira_parcela'] if tipo == Contrato.Tipo.VENDA else ['valor_principal']
        if tipo == Contrato.Tipo.TRADICIONAL:
            obrigatorios += ['qtd_parcelas', 'data_primeira_parcela']
        periodicidade = attrs.get('periodicidade', 'mensal')
        if tipo == Contrato.Tipo.JUROS:
            obrigatorios += ['taxa_juros_mensal', 'valor_juros_mensal']
            attrs['qtd_parcelas'] = None
            if periodicidade not in ('mensal', 'semanal'):
                raise serializers.ValidationError({'periodicidade': 'Somente cobranças mensais ou semanais são permitidas.'})
            obrigatorios.append('dia_semana' if periodicidade == 'semanal' else 'dia_vencimento')
        if periodicidade == 'semanal':
            if not attrs.get('dia_semana'):
                raise serializers.ValidationError({'dia_semana': 'Selecione o dia da semana.'})
            if tipo != Contrato.Tipo.JUROS and attrs.get('data_primeira_parcela') and attrs['data_primeira_parcela'].weekday() != DIAS_SEMANA[attrs['dia_semana']]:
                raise serializers.ValidationError({'data_primeira_parcela': 'O primeiro vencimento deve corresponder ao dia da semana selecionado.'})
            attrs['dia_vencimento'] = None
        else:
            attrs['dia_semana'] = None
        for campo in obrigatorios:
            if attrs.get(campo) in (None, ''):
                raise serializers.ValidationError({campo: 'Este campo é obrigatório para esta modalidade.'})
        if tipo == Contrato.Tipo.VENDA:
            entrada = attrs.get('valor_entrada') or Decimal('0')
            if not attrs.get('teve_entrada'):
                entrada = Decimal('0')
                attrs['valor_entrada'] = entrada
            calcular_por = attrs.get('calcular_por', 'valor_venda')
            if calcular_por == 'valor_parcela':
                if not attrs.get('valor_parcela'):
                    raise serializers.ValidationError({'valor_parcela': 'Informe o valor da parcela.'})
                attrs['valor_venda'] = monetario(attrs['valor_parcela'] * attrs['qtd_parcelas'] + entrada)
            else:
                if not attrs.get('valor_venda'):
                    raise serializers.ValidationError({'valor_venda': 'Informe o valor da venda.'})
                if entrada >= attrs['valor_venda']:
                    raise serializers.ValidationError({'valor_entrada': 'A entrada deve ser menor que o valor da venda.'})
                attrs['valor_parcela'] = monetario((attrs['valor_venda'] - entrada) / attrs['qtd_parcelas'])
        if tipo == Contrato.Tipo.JUROS:
            principal = attrs.get('valor_principal')
            if principal <= 0:
                raise serializers.ValidationError({'valor_principal': 'O valor principal deve ser positivo.'})
            if attrs.get('taxa_juros_mensal') <= 0:
                raise serializers.ValidationError({'taxa_juros_mensal': 'A porcentagem deve ser positiva.'})
            if attrs.get('valor_juros_mensal') <= 0:
                raise serializers.ValidationError({'valor_juros_mensal': 'O valor da parcela deve ser positivo.'})
            attrs['data_primeira_parcela'] = proximo_vencimento_recorrente(periodicidade, attrs.get('dia_vencimento'), attrs.get('dia_semana'))
        if tipo == Contrato.Tipo.TRADICIONAL:
            principal = attrs['valor_principal']
            parcelas = attrs['qtd_parcelas']
            if principal <= 0:
                raise serializers.ValidationError({'valor_principal': 'O valor principal deve ser positivo.'})
            if attrs.get('calcular_emprestimo_por', 'taxa') == 'valor_parcela':
                valor_parcela = attrs.get('valor_parcela')
                if not valor_parcela or valor_parcela <= 0:
                    raise serializers.ValidationError({'valor_parcela': 'Informe o valor da parcela.'})
                if valor_parcela * parcelas <= principal:
                    raise serializers.ValidationError({'valor_parcela': 'O total das parcelas deve ser maior que o valor principal.'})
                attrs['taxa_juros_mensal'] = (((valor_parcela * parcelas / principal) - Decimal('1')) * Decimal('100') / parcelas).quantize(Decimal('0.001'))
            else:
                taxa = attrs.get('taxa_juros_mensal')
                if not taxa or taxa <= 0:
                    raise serializers.ValidationError({'taxa_juros_mensal': 'Informe a porcentagem mensal dos juros.'})
                attrs['valor_parcela'] = monetario(principal * (Decimal('1') + taxa / Decimal('100') * parcelas) / parcelas)
        if attrs.get('origem') == Contrato.Origem.IMPORTADO:
            pagas = attrs.get('qtd_parcelas_pagas', 0)
            total = attrs.get('qtd_parcelas') or 0
            if pagas > total:
                raise serializers.ValidationError({'qtd_parcelas_pagas': 'A quantidade paga não pode exceder o total de parcelas.'})
            if pagas and not attrs.get('forma_pagamento_historico'):
                raise serializers.ValidationError({'forma_pagamento_historico': 'Informe a forma dos pagamentos anteriores.'})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop('calcular_por', None)
        validated_data.pop('calcular_emprestimo_por', None)
        qtd_pagas = validated_data.pop('qtd_parcelas_pagas', 0)
        ultimo_pagamento = validated_data.pop('data_ultimo_pagamento', None)
        forma_historico = validated_data.pop('forma_pagamento_historico', None)
        contrato = Contrato.objects.create(**validated_data)
        gerar_parcelas_do_contrato(contrato)
        if contrato.origem == Contrato.Origem.IMPORTADO:
            parcelas = list(contrato.parcelas.order_by('numero'))
            for indice, parcela in enumerate(parcelas):
                if indice < qtd_pagas:
                    parcela.status = Parcela.Status.PAGA
                    parcela.data_pagamento = ultimo_pagamento if indice == qtd_pagas - 1 and ultimo_pagamento else parcela.data_vencimento
                    parcela.forma_pagamento = forma_historico
                    parcela.valor_pago = parcela.valor
                elif parcela.data_vencimento < date.today():
                    parcela.status = Parcela.Status.ATRASADA
                parcela.save(update_fields=['status', 'data_pagamento', 'forma_pagamento', 'valor_pago'])
            if parcelas and qtd_pagas == len(parcelas):
                contrato.status = Contrato.Status.QUITADO
            elif any(parcela.status == Parcela.Status.ATRASADA for parcela in parcelas):
                contrato.status = Contrato.Status.ATRASADO
            contrato.save(update_fields=['status'])
        return contrato


class ContratoDetailSerializer(serializers.ModelSerializer):
    cliente_nome = serializers.CharField(source='cliente.nome', read_only=True)
    parcelas = ParcelaSerializer(many=True, read_only=True)

    class Meta:
        model = Contrato
        fields = ['id', 'cliente', 'cliente_nome', 'origem', 'tipo', 'status', 'data_inicio', 'produto', 'valor_produto', 'valor_venda', 'teve_entrada', 'valor_entrada', 'valor_principal', 'taxa_juros_mensal', 'qtd_parcelas', 'valor_parcela', 'periodicidade', 'data_primeira_parcela', 'valor_juros_mensal', 'dia_vencimento', 'dia_semana', 'data_quitacao_principal', 'observacoes', 'criado_em', 'parcelas']
        read_only_fields = fields


class ContratoUpdateSerializer(serializers.Serializer):
    produto = serializers.CharField(max_length=160, required=False, allow_blank=True)
    valor_entrada = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'), required=False)
    qtd_parcelas = serializers.IntegerField(min_value=1)
    valor_parcela = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    periodicidade = serializers.ChoiceField(choices=['mensal', 'quinzenal', 'semanal'])
    proximo_vencimento = serializers.DateField()
    dia_semana = serializers.ChoiceField(choices=Contrato.DiaSemana.choices, required=False, allow_null=True)
    observacoes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['periodicidade'] == 'semanal':
            dia_semana = attrs.get('dia_semana')
            if not dia_semana:
                raise serializers.ValidationError({'dia_semana': 'Selecione o dia da semana.'})
            if attrs['proximo_vencimento'].weekday() != DIAS_SEMANA[dia_semana]:
                raise serializers.ValidationError({'proximo_vencimento': 'O próximo vencimento deve corresponder ao dia da semana selecionado.'})
        else:
            attrs['dia_semana'] = None
        return attrs


class ContratoJurosUpdateSerializer(serializers.Serializer):
    valor_principal = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    taxa_juros_mensal = serializers.DecimalField(max_digits=6, decimal_places=3, min_value=Decimal('0.001'))
    valor_juros_mensal = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    periodicidade = serializers.ChoiceField(choices=['mensal', 'semanal'], default='mensal', required=False)
    dia_vencimento = serializers.IntegerField(min_value=1, max_value=31, required=False, allow_null=True)
    dia_semana = serializers.ChoiceField(choices=Contrato.DiaSemana.choices, required=False, allow_null=True)
    observacoes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['periodicidade'] == 'semanal':
            if not attrs.get('dia_semana'):
                raise serializers.ValidationError({'dia_semana': 'Selecione o dia da semana.'})
            attrs['dia_vencimento'] = None
        else:
            if not attrs.get('dia_vencimento'):
                raise serializers.ValidationError({'dia_vencimento': 'Informe o dia do vencimento.'})
            attrs['dia_semana'] = None
        return attrs


class QuitacaoPrincipalSerializer(serializers.Serializer):
    data_pagamento = serializers.DateField(required=False)
    forma_pagamento = serializers.ChoiceField(choices=Parcela.Forma.choices)
