from datetime import date
from decimal import Decimal
from django.db import transaction
from django.db.models import Exists, OuterRef, Q, Sum
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response
from core.models import Contrato, Parcela
from .models import Moto, Aluguel, CobrancaAluguel, LoteAnimal, Movimento
from core.assinatura import view_assinatura, view_pdf_assinado
from .contrato_pdf import contrato_locacao_bytes, contrato_locacao_pdf
from .serializers import MotoSerializer, AluguelSerializer, CobrancaSerializer, LoteSerializer, MovimentoSerializer


class MotosView(generics.ListCreateAPIView):
    serializer_class = MotoSerializer

    def get_queryset(self):
        hoje = timezone.localdate()
        vigentes = Aluguel.objects.filter(moto_id=OuterRef('pk'), inicio__lte=hoje, fim__gte=hoje)
        return Moto.objects.annotate(aluguel_vigente=Exists(vigentes)).order_by('placa')


class CobrancasAluguelView(generics.ListAPIView):
    serializer_class = CobrancaSerializer

    def get_queryset(self):
        hoje = timezone.localdate()
        qs = CobrancaAluguel.objects.select_related('aluguel__cliente', 'aluguel__moto')
        status = self.request.query_params.get('status', '')
        if status:
            filtro = Q(pk__in=[])
            for item in status.split(','):
                if item == 'paga':
                    filtro |= Q(pago_em__isnull=False)
                elif item == 'atrasada':
                    filtro |= Q(pago_em__isnull=True, vencimento__lt=hoje)
                elif item == 'pendente':
                    filtro |= Q(pago_em__isnull=True, vencimento__gte=hoje)
                else:
                    raise serializers.ValidationError({'status': 'Status inválido.'})
            qs = qs.filter(filtro)
        if busca := self.request.query_params.get('busca', '').strip():
            qs = qs.filter(Q(aluguel__cliente__nome__icontains=busca) | Q(aluguel__moto__placa__icontains=busca))
        return qs.order_by('vencimento', 'id')


class AlugueisView(generics.ListCreateAPIView):
    queryset = Aluguel.objects.select_related('moto', 'cliente').prefetch_related('cobrancas').order_by('-inicio', '-id')
    serializer_class = AluguelSerializer


class LotesView(generics.ListCreateAPIView):
    queryset = LoteAnimal.objects.order_by('-id')
    serializer_class = LoteSerializer


class MovimentosView(generics.ListCreateAPIView):
    serializer_class = MovimentoSerializer

    def get_queryset(self):
        qs = Movimento.objects.select_related('moto', 'lote')
        for campo in ('moto', 'lote'):
            if value := self.request.query_params.get(campo):
                if not value.isdigit():
                    raise serializers.ValidationError({campo: 'Informe um identificador válido.'})
                qs = qs.filter(**{campo + '_id': value})
        return qs


@api_view(['POST'])
@transaction.atomic
def receber_aluguel(request, pk):
    cobranca = get_object_or_404(CobrancaAluguel.objects.select_for_update().select_related('aluguel__moto'), pk=pk)
    class PagamentoSerializer(serializers.Serializer):
        data = serializers.DateField()
    serializer = PagamentoSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    pagamento = serializer.validated_data['data']
    if pagamento > date.today():
        raise serializers.ValidationError({'data': 'O pagamento não pode estar no futuro.'})
    if cobranca.pago_em:
        raise serializers.ValidationError('Esta cobrança já foi recebida.')
    cobranca.pago_em = pagamento
    cobranca.save(update_fields=['pago_em'])
    Movimento.objects.create(descricao=f'Aluguel {cobranca.aluguel.moto.placa} · vencimento {cobranca.vencimento}', categoria='aluguel', tipo='entrada', valor=cobranca.valor, data=pagamento, moto=cobranca.aluguel.moto, cobranca=cobranca)
    return Response(CobrancaSerializer(cobranca).data)


@api_view(['GET'])
def contrato_aluguel(request, pk):
    aluguel = get_object_or_404(Aluguel.objects.select_related('moto', 'cliente').prefetch_related('cobrancas'), pk=pk)
    return contrato_locacao_pdf(aluguel)


@api_view(['GET', 'POST'])
def assinatura_aluguel(request, pk):
    aluguel = get_object_or_404(Aluguel.objects.select_related('moto', 'cliente').prefetch_related('cobrancas'), pk=pk)
    return view_assinatura(request, aluguel, lambda: contrato_locacao_bytes(aluguel), f'Locação {aluguel.moto.placa} nº {aluguel.pk:05d} – {aluguel.cliente.nome}', f'contrato-locacao-{aluguel.moto.placa}-{aluguel.pk}.pdf', aluguel.cliente)


@api_view(['GET'])
def assinatura_aluguel_pdf(request, pk):
    aluguel = get_object_or_404(Aluguel.objects.select_related('moto'), pk=pk)
    return view_pdf_assinado(aluguel, f'contrato-locacao-{aluguel.moto.placa}-{pk}-assinado.pdf')


def total(qs, campo='valor'):
    return qs.aggregate(total=Sum(campo))['total'] or Decimal('0')


@api_view(['GET'])
def financeiro(request):
    class PeriodoSerializer(serializers.Serializer):
        inicio = serializers.DateField(default=lambda: date.today().replace(day=1))
        fim = serializers.DateField(default=date.today)
    periodo = PeriodoSerializer(data=request.query_params)
    periodo.is_valid(raise_exception=True)
    inicio, fim = periodo.validated_data['inicio'], periodo.validated_data['fim']
    if fim < inicio:
        raise serializers.ValidationError('A data final deve ser posterior à inicial.')
    movimentos = Movimento.objects.filter(data__range=(inicio, fim)).select_related('moto', 'lote')
    recebimentos = Parcela.objects.filter(status=Parcela.Status.PAGA, data_pagamento__range=(inicio, fim)).select_related('contrato__cliente')
    emprestimos = Contrato.objects.filter(origem=Contrato.Origem.NOVO, tipo__in=[Contrato.Tipo.TRADICIONAL, Contrato.Tipo.JUROS], data_inicio__range=(inicio, fim)).select_related('cliente')
    nomes = {'emprestimos': 'Empréstimos', 'motos': 'Aluguel de motos', 'animais': 'Criação de animais', 'outros': 'Outros'}
    categorias = {chave: {'categoria': chave, 'nome': nome, 'entradas': Decimal('0'), 'saidas': Decimal('0')} for chave, nome in nomes.items()}
    lancamentos = []

    def adicionar(chave, descricao, tipo, valor, data, categoria, referencia):
        valor = valor or Decimal('0')
        categorias[categoria]['entradas' if tipo == 'entrada' else 'saidas'] += valor
        lancamentos.append({'id': chave, 'descricao': descricao, 'tipo': tipo, 'valor': valor, 'data': data, 'categoria': categoria, 'categoria_nome': nomes[categoria], 'referencia': referencia})

    for movimento in movimentos:
        categoria = ('motos' if movimento.moto_id or movimento.categoria in ('motos', 'aluguel', 'manutencao', 'multa') else
                     'animais' if movimento.lote_id or movimento.categoria in ('animais', 'compra_animais', 'alimentacao', 'medicamentos', 'veterinario', 'manejo', 'venda_animais') else
                     'emprestimos' if movimento.categoria == 'emprestimos' else 'outros')
        referencia = movimento.moto.placa if movimento.moto_id else movimento.lote.identificacao if movimento.lote_id else nomes[categoria]
        adicionar(f'movimento-{movimento.pk}', movimento.descricao, movimento.tipo, movimento.valor, movimento.data, categoria, referencia)
    for parcela in recebimentos:
        categoria = 'outros' if parcela.contrato.tipo == Contrato.Tipo.VENDA else 'emprestimos'
        adicionar(f'parcela-{parcela.pk}', f'Recebimento de contrato #{parcela.contrato_id}', 'entrada', parcela.valor_pago, parcela.data_pagamento, categoria, parcela.contrato.cliente.nome)
    for contrato in emprestimos:
        adicionar(f'capital-{contrato.pk}', f'Capital emprestado · contrato #{contrato.pk}', 'saida', contrato.valor_principal, contrato.data_inicio, 'emprestimos', contrato.cliente.nome)
    entradas = sum((item['entradas'] for item in categorias.values()), Decimal('0'))
    saidas = sum((item['saidas'] for item in categorias.values()), Decimal('0'))
    for item in categorias.values():
        item['saldo'] = item['entradas'] - item['saidas']
    lancamentos.sort(key=lambda item: (item['data'], item['id']), reverse=True)
    lotes = []
    # Resultado acumulado por lote; não depende do filtro de caixa mensal.
    for lote in LoteAnimal.objects.prefetch_related('movimentos').order_by('identificacao'):
        entradas_lote = sum((m.valor for m in lote.movimentos.all() if m.tipo == 'entrada'), Decimal('0'))
        despesas = sum((m.valor for m in lote.movimentos.all() if m.tipo == 'saida'), Decimal('0'))
        lotes.append({'id': lote.pk, 'nome': lote.identificacao, 'receitas': entradas_lote, 'despesas': despesas, 'resultado': entradas_lote - despesas})
    return Response({'inicio': inicio, 'fim': fim, 'entradas': entradas, 'saidas': saidas, 'saldo_periodo': entradas - saidas, 'recebido_emprestimos': total(recebimentos, 'valor_pago'), 'capital_emprestado': total(emprestimos, 'valor_principal'), 'lotes': lotes, 'categorias': list(categorias.values()), 'lancamentos': lancamentos})
