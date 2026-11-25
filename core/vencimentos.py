from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from core.models import Contrato, Parcela
from operacoes.models import Aluguel, CobrancaAluguel


class VencimentoSerializer(serializers.Serializer):
    vencimento = serializers.DateField()
    vencimento_atual = serializers.DateField()


def editar(request, pk, aluguel=False):
    modelo = CobrancaAluguel if aluguel else Parcela
    modelo_pai = Aluguel if aluguel else Contrato
    relacao = 'aluguel' if aluguel else 'contrato'
    campo = 'vencimento' if aluguel else 'data_vencimento'
    original = 'vencimento_original' if aluguel else 'data_vencimento_original'
    item = get_object_or_404(modelo, pk=pk)
    with transaction.atomic():
        pai = get_object_or_404(modelo_pai.objects.select_for_update(), pk=getattr(item, relacao+'_id'))
        item = modelo.objects.select_for_update().get(pk=pk)
        if aluguel:
            if item.pago_em or item.transferida_para_id:
                raise ValidationError('Cobrança paga ou transferida não pode ter o vencimento alterado.')
        elif item.status not in [Parcela.Status.PENDENTE, Parcela.Status.ATRASADA] or pai.status not in [Contrato.Status.ATIVO, Contrato.Status.ATRASADO]:
            raise ValidationError('Somente cobranças em aberto podem ter o vencimento alterado.')
        atual = getattr(item, campo)
        if request.method == 'GET':
            return Response({'vencimento': atual, 'vencimento_original': getattr(item, original), 'valor': str(item.valor)})
        serializer = VencimentoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        novo = serializer.validated_data['vencimento']
        if serializer.validated_data['vencimento_atual'] != atual:
            return Response({'detail': 'O vencimento mudou. Reabra a opção para conferir a data atual.'}, status=409)
        inicio = pai.inicio if aluguel else pai.data_inicio
        if novo < inicio:
            raise ValidationError({'vencimento': 'O vencimento não pode ser anterior ao início do contrato.'})
        if aluguel and pai.cobrancas.exclude(pk=pk).filter(vencimento=novo).exists():
            raise ValidationError({'vencimento': 'Já existe outra cobrança deste aluguel nessa data. Use Juntar à próxima se quiser somar valores.'})
        if novo != atual:
            if getattr(item, original) is None:
                setattr(item, original, atual)
            setattr(item, campo, novo)
            campos = [campo, original]
            if not aluguel:
                item.status = Parcela.Status.ATRASADA if novo < timezone.localdate() else Parcela.Status.PENDENTE
                campos.append('status')
            item.save(update_fields=campos)
            if not aluguel:
                atrasado = pai.parcelas.filter(status__in=[Parcela.Status.PENDENTE, Parcela.Status.ATRASADA], data_vencimento__lt=timezone.localdate()).exists()
                pai.status = Contrato.Status.ATRASADO if atrasado else Contrato.Status.ATIVO
                pai.save(update_fields=['status'])
        return Response({'id': item.pk, 'vencimento': getattr(item, campo), 'vencimento_original': getattr(item, original), 'valor': str(item.valor)})


@api_view(['GET', 'PATCH'])
def vencimento_parcela(request, pk):
    return editar(request, pk)


@api_view(['GET', 'PATCH'])
def vencimento_aluguel(request, pk):
    return editar(request, pk, aluguel=True)
