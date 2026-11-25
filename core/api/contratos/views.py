from datetime import date
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from core.models import Contrato, MensagemEnviada, Parcela
from core.api.parcelas.serializers import ParcelaSerializer
from core.assinatura import resumo, view_pdf_assinado
from .instrumento import contrato_mutuo_pdf
from .pdf import comprovante_pdf
from .serializers import ContratoCreateSerializer, ContratoDetailSerializer, ContratoJurosUpdateSerializer, ContratoUpdateSerializer, QuitacaoPrincipalSerializer
from .services import adicionar_periodo, proximo_vencimento_recorrente


class ContratoCreateView(generics.ListCreateAPIView):
    def get_serializer_class(self):
        return ContratoCreateSerializer if self.request.method == 'POST' else ContratoDetailSerializer

    def get_queryset(self):
        queryset = Contrato.objects.select_related('cliente').prefetch_related('parcelas').order_by('-criado_em')
        if cliente_id := self.request.query_params.get('cliente'):
            queryset = queryset.filter(cliente_id=cliente_id)
        if tipo := self.request.query_params.get('tipo'):
            queryset = queryset.filter(tipo=tipo)
        if status_value := self.request.query_params.get('status'):
            queryset = queryset.filter(status=status_value)
        if busca := self.request.query_params.get('busca'):
            queryset = queryset.filter(cliente__nome__icontains=busca)
        return queryset


class ContratoDetailView(generics.RetrieveAPIView):
    queryset = Contrato.objects.select_related('cliente').prefetch_related('parcelas')
    serializer_class = ContratoDetailSerializer


@api_view(['POST'])
@transaction.atomic
def concluir_contrato(request, pk):
    contrato = get_object_or_404(
        Contrato.objects.select_for_update().prefetch_related('parcelas'), pk=pk
    )
    if contrato.status == Contrato.Status.QUITADO:
        return Response({'detail': 'Este contrato já está concluído.'}, status=400)

    parcelas_abertas = contrato.parcelas.exclude(status=Parcela.Status.PAGA)
    MensagemEnviada.objects.filter(parcela__in=parcelas_abertas).delete()
    parcelas_abertas.delete()
    contrato.status = Contrato.Status.QUITADO
    contrato.save(update_fields=['status'])

    contrato_atualizado = Contrato.objects.select_related('cliente').prefetch_related('parcelas').get(pk=contrato.pk)
    return Response(ContratoDetailSerializer(contrato_atualizado).data)


@api_view(['DELETE'])
@transaction.atomic
def excluir_contrato(request, pk):
    contrato = get_object_or_404(
        Contrato.objects.select_for_update().prefetch_related('parcelas'), pk=pk
    )
    MensagemEnviada.objects.filter(parcela__contrato=contrato).delete()
    contrato.parcelas.all().delete()
    contrato.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@transaction.atomic
def quitar_principal(request, pk):
    contrato = get_object_or_404(Contrato, pk=pk, tipo=Contrato.Tipo.JUROS, status__in=[Contrato.Status.ATIVO, Contrato.Status.ATRASADO])
    serializer = QuitacaoPrincipalSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    dados = serializer.validated_data
    pagamento = dados.get('data_pagamento', date.today())
    contrato.parcelas.filter(tipo=Parcela.Tipo.JUROS).exclude(status=Parcela.Status.PAGA).delete()
    parcela = Parcela.objects.create(contrato=contrato, tipo=Parcela.Tipo.QUITACAO, valor=contrato.valor_principal, data_vencimento=pagamento, status=Parcela.Status.PAGA, data_pagamento=pagamento, forma_pagamento=dados['forma_pagamento'], valor_pago=contrato.valor_principal)
    contrato.data_quitacao_principal = pagamento
    contrato.status = Contrato.Status.QUITADO
    contrato.save(update_fields=['data_quitacao_principal', 'status'])
    return Response(ParcelaSerializer(parcela).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def comprovante(request, pk):
    contrato = get_object_or_404(Contrato.objects.select_related('cliente').prefetch_related('parcelas'), pk=pk)
    return comprovante_pdf(contrato)


@api_view(['GET'])
def instrumento(request, pk):
    contrato = get_object_or_404(Contrato.objects.select_related('cliente').prefetch_related('parcelas'), pk=pk)
    if contrato.tipo == Contrato.Tipo.VENDA:
        return Response({'detail': 'O contrato de mútuo está disponível apenas para empréstimos.'}, status=status.HTTP_400_BAD_REQUEST)
    return contrato_mutuo_pdf(contrato)


@api_view(['GET'])
def assinatura(request, pk):
    contrato = get_object_or_404(Contrato, pk=pk)
    return Response({**resumo(contrato), 'configurado': False, 'detail': 'Assinatura eletrônica disponível somente para aluguel de moto.'})


@api_view(['GET'])
def assinatura_pdf(request, pk):
    return view_pdf_assinado(get_object_or_404(Contrato, pk=pk), f'contrato-mutuo-{pk}-assinado.pdf')


@api_view(['PATCH'])
@transaction.atomic
def editar_contrato(request, pk):
    contrato = get_object_or_404(Contrato.objects.select_for_update().prefetch_related('parcelas'), pk=pk)
    if contrato.tipo == Contrato.Tipo.JUROS:
        serializer = ContratoJurosUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data
        abertas = list(contrato.parcelas.select_for_update().filter(tipo=Parcela.Tipo.JUROS).exclude(status=Parcela.Status.PAGA))
        if not abertas:
            return Response({'detail': 'Este contrato não possui cobrança aberta para editar.'}, status=400)
        vencimento = proximo_vencimento_recorrente(dados['periodicidade'], dados.get('dia_vencimento'), dados.get('dia_semana'))
        for parcela in abertas:
            parcela.valor = dados['valor_juros_mensal']
            parcela.data_vencimento = vencimento
            parcela.status = Parcela.Status.PENDENTE
        Parcela.objects.bulk_update(abertas, ['valor', 'data_vencimento', 'status'])
        contrato.valor_principal = dados['valor_principal']
        contrato.taxa_juros_mensal = dados['taxa_juros_mensal']
        contrato.valor_juros_mensal = dados['valor_juros_mensal']
        contrato.periodicidade = dados['periodicidade']
        contrato.dia_vencimento = dados['dia_vencimento']
        contrato.dia_semana = dados['dia_semana']
        contrato.data_primeira_parcela = vencimento
        contrato.observacoes = dados.get('observacoes', contrato.observacoes)
        contrato.status = Contrato.Status.ATIVO
        contrato.save()
        contrato_atualizado = Contrato.objects.select_related('cliente').prefetch_related('parcelas').get(pk=contrato.pk)
        return Response(ContratoDetailSerializer(contrato_atualizado).data)
    serializer = ContratoUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    dados = serializer.validated_data
    abertas = list(contrato.parcelas.select_for_update().exclude(status=Parcela.Status.PAGA).order_by('numero', 'data_vencimento'))
    if not abertas:
        return Response({'detail': 'Este contrato não possui cobranças abertas para editar.'}, status=400)
    pagas = list(contrato.parcelas.select_for_update().filter(status=Parcela.Status.PAGA))
    quantidade = dados['qtd_parcelas']
    maior_numero_pago = max((parcela.numero or 0 for parcela in pagas), default=0)
    if quantidade < maior_numero_pago:
        return Response({'qtd_parcelas': f'A quantidade não pode ser menor que a parcela {maior_numero_pago}, que já foi paga.'}, status=400)
    numeros_pagos = {parcela.numero for parcela in pagas}
    numeros_abertos = [numero for numero in range(1, quantidade + 1) if numero not in numeros_pagos]
    excedentes = abertas[len(numeros_abertos):]
    if excedentes:
        Parcela.objects.filter(pk__in=[parcela.pk for parcela in excedentes]).delete()
    abertas = abertas[:len(numeros_abertos)]
    for numero in numeros_abertos[len(abertas):]:
        abertas.append(Parcela(contrato=contrato, numero=numero, valor=dados['valor_parcela'], data_vencimento=dados['proximo_vencimento']))
    for indice, parcela in enumerate(abertas):
        parcela.numero = numeros_abertos[indice]
        parcela.valor = dados['valor_parcela']
        parcela.data_vencimento = adicionar_periodo(dados['proximo_vencimento'], indice, dados['periodicidade'])
        parcela.status = Parcela.Status.ATRASADA if parcela.data_vencimento < date.today() else Parcela.Status.PENDENTE
    novas = [parcela for parcela in abertas if parcela.pk is None]
    existentes = [parcela for parcela in abertas if parcela.pk is not None]
    if novas:
        Parcela.objects.bulk_create(novas)
    if existentes:
        Parcela.objects.bulk_update(existentes, ['numero', 'valor', 'data_vencimento', 'status'])
    contrato.qtd_parcelas = quantidade
    contrato.valor_parcela = dados['valor_parcela']
    contrato.periodicidade = dados['periodicidade']
    contrato.dia_semana = dados['dia_semana']
    contrato.data_primeira_parcela = contrato.parcelas.order_by('numero', 'data_vencimento').first().data_vencimento
    contrato.produto = dados.get('produto', contrato.produto)
    contrato.observacoes = dados.get('observacoes', contrato.observacoes)
    if contrato.tipo == Contrato.Tipo.VENDA:
        contrato.valor_entrada = dados.get('valor_entrada', contrato.valor_entrada)
        contrato.teve_entrada = contrato.valor_entrada > 0
        contrato.valor_venda = (contrato.valor_entrada or 0) + sum(contrato.parcelas.values_list('valor', flat=True))
    contrato.status = Contrato.Status.ATRASADO if any(item.status == Parcela.Status.ATRASADA for item in abertas) else Contrato.Status.ATIVO
    contrato.save()
    contrato_atualizado = Contrato.objects.select_related('cliente').prefetch_related('parcelas').get(pk=contrato.pk)
    return Response(ContratoDetailSerializer(contrato_atualizado).data)
