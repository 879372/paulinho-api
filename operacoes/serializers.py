from datetime import date
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from core.api.contratos.services import adicionar_periodo
from .cadastro import cadastro_completo
from .models import Moto, Aluguel, CobrancaAluguel, LoteAnimal, Movimento


class MotoSerializer(serializers.ModelSerializer):
    disponibilidade = serializers.SerializerMethodField()

    def get_disponibilidade(self, obj):
        if obj.em_manutencao:
            return 'manutencao'
        alugada = getattr(obj, 'aluguel_vigente', None)
        if alugada is None:
            hoje = timezone.localdate()
            alugada = obj.alugueis.filter(inicio__lte=hoje, fim__gte=hoje).exists()
        return 'alugada' if alugada else 'disponivel'

    class Meta:
        model = Moto
        fields = '__all__'

    def validate_placa(self, value):
        import re
        value = value.upper().replace('-', '').replace(' ', '')
        if not re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9][0-9]{2}', value):
            raise serializers.ValidationError('Informe uma placa brasileira válida.')
        if Moto.objects.exclude(pk=self.instance.pk if self.instance else None).filter(placa=value).exists():
            raise serializers.ValidationError('Esta placa já está cadastrada.')
        return value


class CobrancaSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    cliente_nome = serializers.CharField(source='aluguel.cliente.nome', read_only=True)
    placa = serializers.CharField(source='aluguel.moto.placa', read_only=True)

    class Meta:
        model = CobrancaAluguel
        fields = ['id', 'aluguel', 'vencimento', 'vencimento_original', 'valor', 'pago_em', 'cliente_nome', 'placa', 'status', 'transferida_para']
        read_only_fields = fields


    def get_status(self, obj):
        if obj.transferida_para_id:
            return 'transferida'
        if obj.pago_em:
            return 'paga'
        return 'atrasada' if obj.vencimento < timezone.localdate() else 'pendente'


class AluguelSerializer(serializers.ModelSerializer):
    caucao_financeiro = serializers.SerializerMethodField()

    def get_caucao_financeiro(self, obj):
        def movimento(item):
            return {'id': item.pk, 'data': item.data, 'valor': item.valor} if item else None
        return {'recebimento': movimento(obj.caucao_recebimento), 'devolucao': movimento(obj.caucao_devolucao)}

    cadastro_completo = serializers.SerializerMethodField()

    def get_cadastro_completo(self, obj):
        return cadastro_completo(obj)

    cliente_nome = serializers.CharField(source='cliente.nome', read_only=True)
    placa = serializers.CharField(source='moto.placa', read_only=True)
    cobrancas = CobrancaSerializer(many=True, read_only=True)

    class Meta:
        model = Aluguel
        exclude = ['assinatura_id', 'cadastro_token_hash', 'dados_locatario']
        read_only_fields = ['caucao_recebimento', 'caucao_devolucao', 'assinatura_status', 'assinatura_enviada_em', 'assinatura_concluida_em', 'assinatura_link_empresa', 'assinatura_sandbox', 'cadastro_expira_em', 'cadastro_preenchido_em']

    def validate(self, attrs):
        if attrs['fim'] < attrs['inicio']:
            raise serializers.ValidationError({'fim': 'O término deve ser igual ou posterior ao início.'})
        if (attrs['fim'] - attrs['inicio']).days > 3660:
            raise serializers.ValidationError({'fim': 'O prazo máximo é de dez anos.'})
        if not attrs['inicio'] <= attrs['primeiro_vencimento'] <= attrs['fim']:
            raise serializers.ValidationError({'primeiro_vencimento': 'O vencimento deve estar dentro do período do contrato.'})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        moto = Moto.objects.select_for_update().get(pk=validated_data['moto'].pk)
        if moto.em_manutencao:
            raise serializers.ValidationError({'moto': 'Esta moto está em manutenção.'})
        if moto.alugueis.filter(inicio__lte=validated_data['fim'], fim__gte=validated_data['inicio']).exists():
            raise serializers.ValidationError({'moto': 'A moto já possui aluguel nesse período.'})
        aluguel = Aluguel.objects.create(**validated_data)
        indice = 0
        while True:
            vencimento = adicionar_periodo(aluguel.primeiro_vencimento, indice, aluguel.periodicidade)
            if vencimento > aluguel.fim:
                break
            CobrancaAluguel.objects.create(aluguel=aluguel, vencimento=vencimento, valor=aluguel.valor)
            indice += 1
        return aluguel


class LoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoteAnimal
        fields = '__all__'

    def validate_data_aquisicao(self, value):
        if value > date.today():
            raise serializers.ValidationError('A compra não pode estar no futuro.')
        return value

    @transaction.atomic
    def create(self, validated_data):
        lote = super().create(validated_data)
        if lote.valor_compra:
            Movimento.objects.create(descricao=f'Compra: {lote.identificacao}', categoria='compra_animais', tipo='saida', valor=lote.valor_compra, data=lote.data_aquisicao, lote=lote)
        return lote


class MovimentoSerializer(serializers.ModelSerializer):
    referencia = serializers.SerializerMethodField()

    class Meta:
        model = Movimento
        fields = '__all__'
        read_only_fields = ['cobranca']

    def get_referencia(self, obj):
        return obj.lote.identificacao if obj.lote_id else obj.moto.placa if obj.moto_id else 'Geral'

    def validate(self, attrs):
        if attrs.get('moto') and attrs.get('lote'):
            raise serializers.ValidationError('Vincule o lançamento a uma moto ou a um lote.')
        if attrs['data'] > date.today():
            raise serializers.ValidationError({'data': 'Registre apenas entradas e despesas já realizadas.'})
        categoria = attrs['categoria']
        if categoria in ('compra_animais', 'aluguel'):
            raise serializers.ValidationError({'categoria': 'Esta categoria é gerada automaticamente.'})
        if categoria in ('alimentacao', 'medicamentos', 'veterinario', 'manejo', 'venda_animais') and not attrs.get('lote'):
            raise serializers.ValidationError({'lote': 'Selecione o lote de animais.'})
        if categoria in ('manutencao', 'multa') and not attrs.get('moto'):
            raise serializers.ValidationError({'moto': 'Selecione a moto.'})
        if categoria == 'venda_animais' and attrs['tipo'] != 'entrada':
            raise serializers.ValidationError({'tipo': 'Venda de animais deve ser uma entrada.'})
        if categoria in ('alimentacao', 'medicamentos', 'veterinario', 'manejo', 'manutencao', 'multa') and attrs['tipo'] != 'saida':
            raise serializers.ValidationError({'tipo': 'Esta categoria deve ser uma despesa.'})
        return attrs
