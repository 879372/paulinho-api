import hashlib
import secrets
from datetime import timedelta
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from .models import Aluguel

ESTADOS_CIVIS = [('solteiro', 'Solteiro(a)'), ('casado', 'Casado(a)'), ('divorciado', 'Divorciado(a)'), ('viuvo', 'Viúvo(a)'), ('uniao_estavel', 'União estável'), ('separado', 'Separado(a)')]
UFS = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split()


def digitos(value):
    return ''.join(c for c in value if c in '0123456789')


class DadosLocatarioSerializer(serializers.Serializer):
    nome = serializers.CharField(max_length=160, min_length=3)
    cpf = serializers.CharField(max_length=18)
    rg = serializers.CharField(max_length=25, min_length=3)
    orgao_emissor = serializers.CharField(max_length=40, min_length=2)
    nacionalidade = serializers.CharField(max_length=60, min_length=3)
    estado_civil = serializers.ChoiceField(choices=ESTADOS_CIVIS)
    profissao = serializers.CharField(max_length=100, min_length=2)
    telefone = serializers.CharField(max_length=20)
    cnh_numero = serializers.CharField(max_length=20)
    cnh_categoria = serializers.ChoiceField(choices=['A', 'AB', 'AC', 'AD', 'AE'])
    cnh_validade = serializers.DateField()
    cep = serializers.CharField(max_length=10)
    logradouro = serializers.CharField(max_length=160, min_length=3)
    numero = serializers.CharField(max_length=20)
    complemento = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    bairro = serializers.CharField(max_length=100, min_length=2)
    cidade = serializers.CharField(max_length=100, min_length=2)
    uf = serializers.ChoiceField(choices=UFS)
    confirmacao = serializers.BooleanField()

    def validate_nome(self, value):
        if len(value.split()) < 2:
            raise serializers.ValidationError('Informe o nome completo.')
        return value

    def validate_cpf(self, value):
        value = digitos(value)
        if len(value) != 11 or len(set(value)) == 1:
            raise serializers.ValidationError('Informe um CPF válido.')
        for tamanho in (9, 10):
            verificador = sum(int(value[i]) * (tamanho + 1 - i) for i in range(tamanho)) * 10 % 11
            if int(value[tamanho]) != (0 if verificador == 10 else verificador):
                raise serializers.ValidationError('Informe um CPF válido.')
        return value

    def validate_telefone(self, value):
        value = digitos(value)
        if len(value) in (10, 11):
            value = '55' + value
        if not value.startswith('55') or len(value) not in (12, 13):
            raise serializers.ValidationError('Informe telefone com DDD.')
        return value

    def validate_cnh_numero(self, value):
        value = digitos(value)
        if len(value) != 11 or len(set(value)) == 1:
            raise serializers.ValidationError('A CNH deve conter 11 dígitos.')
        return value

    def validate_cnh_validade(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError('A CNH está vencida. Informe uma habilitação válida.')
        return value

    def validate_cep(self, value):
        value = digitos(value)
        if len(value) != 8:
            raise serializers.ValidationError('Informe um CEP com 8 dígitos.')
        return value

    def validate_confirmacao(self, value):
        if not value:
            raise serializers.ValidationError('Confirme a conferência dos dados.')
        return value


def cadastro_completo(aluguel):
    if not aluguel.cadastro_preenchido_em:
        return False
    return DadosLocatarioSerializer(data=aluguel.dados_locatario).is_valid()


def resumo_cadastro(aluguel):
    return {'cadastro_completo': cadastro_completo(aluguel), 'cadastro_preenchido_em': aluguel.cadastro_preenchido_em,
            'cadastro_expira_em': aluguel.cadastro_expira_em,
            'link_ativo': bool(aluguel.cadastro_token_hash and aluguel.cadastro_expira_em and aluguel.cadastro_expira_em > timezone.now())}


@api_view(['GET', 'POST'])
@transaction.atomic
def gerenciar_cadastro(request, pk):
    aluguel = get_object_or_404(Aluguel.objects.select_for_update(), pk=pk)
    if request.method == 'GET':
        return Response(resumo_cadastro(aluguel))
    if aluguel.assinatura_status in ('pendente', 'assinado'):
        return Response({'detail': 'O contrato já foi enviado para assinatura. Não é possível reabrir o cadastro.'}, status=400)
    if aluguel.cadastro_preenchido_em and request.data.get('reabrir') is not True:
        return Response({'detail': 'Confirme a reabertura para corrigir o cadastro já preenchido.'}, status=400)
    token = secrets.token_urlsafe(32)
    aluguel.cadastro_token_hash = hashlib.sha256(token.encode()).hexdigest()
    aluguel.cadastro_expira_em = timezone.now() + timedelta(days=7)
    aluguel.cadastro_preenchido_em = None
    aluguel.save(update_fields=['cadastro_token_hash', 'cadastro_expira_em', 'cadastro_preenchido_em'])
    return Response({**resumo_cadastro(aluguel), 'token': token}, status=201)


class CadastroPublicoThrottle(SimpleRateThrottle):
    rate = '30/hour'
    scope = 'cadastro_publico'
    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


def obter_por_token(request, bloquear=False):
    class TokenSerializer(serializers.Serializer):
        token = serializers.CharField(min_length=40, max_length=100, trim_whitespace=False)
    serializer = TokenSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    token_hash = hashlib.sha256(serializer.validated_data['token'].encode()).hexdigest()
    qs = Aluguel.objects.select_for_update() if bloquear else Aluguel.objects
    aluguel = get_object_or_404(qs.select_related('moto'), cadastro_token_hash=token_hash)
    if not aluguel.cadastro_expira_em or aluguel.cadastro_expira_em <= timezone.now():
        return None
    return aluguel


def resposta_publica(aluguel):
    return {'concluido': bool(aluguel.cadastro_preenchido_em), 'contrato': aluguel.pk, 'placa': aluguel.moto.placa,
            'modelo': aluguel.moto.modelo, 'inicio': aluguel.inicio, 'fim': aluguel.fim, 'expira_em': aluguel.cadastro_expira_em}


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([CadastroPublicoThrottle])
def consultar_publico(request):
    aluguel = obter_por_token(request)
    if aluguel is None:
        return Response({'detail': 'Este link expirou. Solicite um novo link à locadora.'}, status=410)
    return Response(resposta_publica(aluguel))


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([CadastroPublicoThrottle])
@transaction.atomic
def concluir_publico(request):
    aluguel = obter_por_token(request, bloquear=True)
    if aluguel is None:
        return Response({'detail': 'Este link expirou. Solicite um novo link à locadora.'}, status=410)
    if aluguel.cadastro_preenchido_em or aluguel.assinatura_status in ('pendente', 'assinado'):
        return Response({'detail': 'Este cadastro já foi concluído e não pode ser alterado por este link.'}, status=409)
    dados_recebidos = request.data.get('dados')
    if not isinstance(dados_recebidos, dict):
        raise serializers.ValidationError({'dados': 'Preencha os dados do formulário.'})
    serializer = DadosLocatarioSerializer(data=dados_recebidos)
    serializer.is_valid(raise_exception=True)
    dados = dict(serializer.validated_data)
    dados['cnh_validade'] = dados['cnh_validade'].isoformat()
    aluguel.dados_locatario = dados
    aluguel.cadastro_preenchido_em = timezone.now()
    aluguel.save(update_fields=['dados_locatario', 'cadastro_preenchido_em'])
    return Response({'concluido': True, 'detail': 'Dados enviados. A locadora poderá encaminhar o contrato para assinatura separadamente.'})
