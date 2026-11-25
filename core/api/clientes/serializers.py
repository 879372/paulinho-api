import re
from rest_framework import serializers
from core.models import Cliente
from core.api.contratos.serializers import ContratoDetailSerializer


def normalizar_telefone(value):
    telefone = re.sub(r'\D', '', value)
    if telefone.startswith('55') and len(telefone) in (12, 13):
        telefone = telefone[2:]
    return telefone


class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = ['id', 'nome', 'telefone', 'cpf', 'endereco', 'observacoes', 'criado_em']
        read_only_fields = ['id', 'criado_em']

    def validate_telefone(self, value):
        telefone = normalizar_telefone(value)
        if len(telefone) not in range(10, 16):
            raise serializers.ValidationError('Informe um telefone válido (BR ou E.164).')
        cliente_atual = self.instance.pk if self.instance else None
        telefones_cadastrados = Cliente.objects.exclude(pk=cliente_atual).values_list('telefone', flat=True)
        if any(normalizar_telefone(cadastrado) == telefone for cadastrado in telefones_cadastrados):
            raise serializers.ValidationError('Já existe um cliente cadastrado com este telefone.')
        return telefone

    def validate(self, attrs):
        # PostgreSQL permite vários valores NULL em uma coluna única, mas não
        # vários textos vazios. O formulário envia "" quando o CPF é opcional.
        if 'cpf' in attrs and not attrs['cpf']:
            attrs['cpf'] = None
        return attrs


class ClienteDetailSerializer(ClienteSerializer):
    contratos = ContratoDetailSerializer(many=True, read_only=True)

    class Meta(ClienteSerializer.Meta):
        fields = [*ClienteSerializer.Meta.fields, 'contratos']
