from decimal import Decimal
from django.utils import timezone
from reportlab.platypus import KeepTogether, Spacer
from core.pdf_visual import header, metrics, cards, section, grid, p, response


def moeda(valor):
    valor = Decimal(valor or 0)
    return f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def data_br(data):
    return data.strftime('%d/%m/%Y') if data else '-'


def status_label(status):
    return {'paga': 'Paga', 'atrasada': 'Em atraso', 'pendente': 'Pendente', 'transferida': 'Transferida'}.get(status, status.title())


def comprovante_pdf(contrato):
    parcelas = list(contrato.parcelas.all())
    total = sum((item.valor for item in parcelas if item.status != 'transferida'), Decimal('0'))
    recebido = sum((item.valor_pago if item.valor_pago is not None else item.valor for item in parcelas if item.status == 'paga'), Decimal('0'))
    aberto = sum((item.valor for item in parcelas if item.status in ('pendente', 'atrasada')), Decimal('0'))
    story = header('Comprovante de contrato', f'Contrato #{contrato.pk:05d} · {contrato.get_tipo_display()}')
    story.append(metrics([('Total das cobranças', moeda(total)), ('Recebido', moeda(recebido)), ('Em aberto', moeda(aberto))]))
    story.extend([section('Dados do cliente'), cards([('Nome', contrato.cliente.nome), ('Telefone', contrato.cliente.telefone), ('CPF', contrato.cliente.cpf or 'Não informado'), ('Endereço', contrato.cliente.endereco or 'Não informado')])])
    if contrato.tipo == 'venda':
        detalhes = [('Produto', contrato.produto or 'Não informado'), ('Valor da venda', moeda(contrato.valor_venda)), ('Entrada recebida', moeda(contrato.valor_entrada)), ('Valor parcelado', moeda((contrato.valor_venda or 0)-(contrato.valor_entrada or 0))), ('Condição', f'{contrato.qtd_parcelas} parcelas de {moeda(contrato.valor_parcela)} · {contrato.periodicidade.title()}')]
    else:
        detalhes = [('Valor a receber' if contrato.tipo == 'emprestimo_somente_juros' else 'Valor passado', moeda(contrato.valor_principal)), ('Juros informado', f'{contrato.taxa_juros_mensal or 0}% ao mês'), ('Cobrança periódica', moeda(contrato.valor_parcela or contrato.valor_juros_mensal)), ('Condição', f'{contrato.qtd_parcelas} parcelas' if contrato.qtd_parcelas else 'Recorrente até quitar o principal')]
        if contrato.tipo == 'emprestimo_somente_juros':
            detalhes.append(('Principal para quitação', moeda(contrato.valor_principal)))
    detalhes += [('Início', data_br(contrato.data_inicio))]
    story.extend([section('Detalhes da operação'), cards(detalhes), section('Cronograma de parcelas')])
    hoje = timezone.localdate()
    rows = []
    for item in parcelas:
        status = 'atrasada' if item.status in ('pendente', 'atrasada') and item.data_vencimento < hoje else item.status
        rows.append([str(item.numero or ('Quitação' if item.tipo == 'quitacao_principal' else 'Juros' if item.tipo == 'juros_mensal' else 'Saldo')), data_br(item.data_vencimento), moeda(item.valor), data_br(item.data_pagamento), status_label(status)])
    story.append(grid(['Parcela', 'Vencimento', 'Valor', 'Pagamento', 'Status'], rows, [.13,.22,.23,.22,.20]))
    declaracao = [Spacer(1,12),p('O cliente declara ciência das informações desta operação e dos valores e vencimentos indicados neste documento.', 'small')]
    if contrato.observacoes:
        declaracao += [Spacer(1,8),p('Observações: '+contrato.observacoes)]
    declaracao += [Spacer(1,12),p('________________________________________________'),p('Assinatura do cliente', 'small'),Spacer(1,9),p('Local e data: ____________________________________', 'small')]
    story.append(KeepTogether(declaracao))
    return response(story, f'Comprovante do contrato {contrato.pk}', f'comprovante-contrato-{contrato.pk}.pdf')
