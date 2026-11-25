from decimal import Decimal
from reportlab.platypus import KeepTogether, Spacer
from core.models import Contrato, Parcela


def moeda(valor):
    valor = Decimal(valor or 0)
    return f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def data_br(valor):
    return valor.strftime('%d/%m/%Y') if valor else '-'


def status_label(status):
    return {
        Contrato.Status.ATIVO: 'Ativo', Contrato.Status.ATRASADO: 'Atrasado',
        Contrato.Status.QUITADO: 'Quitado', Contrato.Status.RENEGOCIADO: 'Renegociado',
        Contrato.Status.CANCELADO: 'Cancelado', Parcela.Status.PAGA: 'Paga',
        Parcela.Status.PENDENTE: 'Pendente', Parcela.Status.ATRASADA: 'Em atraso', Parcela.Status.TRANSFERIDA: 'Transferida',
    }.get(status, status.title())


def valor_quitacao(contrato):
    if contrato.status in [Contrato.Status.QUITADO, Contrato.Status.CANCELADO, Contrato.Status.RENEGOCIADO]:
        return Decimal('0')
    if contrato.tipo == Contrato.Tipo.JUROS:
        return contrato.valor_principal or Decimal('0')
    return sum((parcela.valor for parcela in contrato.parcelas.all() if parcela.status not in (Parcela.Status.PAGA, Parcela.Status.TRANSFERIDA)), Decimal('0'))


def valor_emprestado_somente_juros(contrato):
    valor_a_receber = contrato.valor_principal or Decimal('0')
    juros = contrato.valor_juros_mensal or contrato.valor_parcela or Decimal('0')
    return max(valor_a_receber - juros, Decimal('0'))


def relatorio_cliente_pdf(cliente):
    from django.utils import timezone
    from core.pdf_visual import header, metrics, fields, section, grid, p, response
    contratos = list(cliente.contratos.all())
    total_quitacao = sum((valor_quitacao(c) for c in contratos), Decimal('0'))
    story = header('Relatório financeiro', f'Cliente #{cliente.pk:05d}')
    story.extend([p(cliente.nome, 'brand'), p(f'Telefone: {cliente.telefone} · CPF: {cliente.cpf or "Não informado"}', 'small'), Spacer(1,16)])
    story.append(metrics([('Contratos', str(len(contratos))), ('Total para quitação', moeda(total_quitacao))]))
    grupos = [(Contrato.Tipo.VENDA, 'Produtos'), (Contrato.Tipo.TRADICIONAL, 'Empréstimos'), (Contrato.Tipo.JUROS, 'Empréstimos somente juros')]
    hoje = timezone.localdate()
    for tipo, rotulo in grupos:
        itens = [c for c in contratos if c.tipo == tipo]
        if not itens:
            continue
        for indice, contrato in enumerate(itens):
            nome = contrato.produto if tipo == Contrato.Tipo.VENDA and contrato.produto else contrato.get_tipo_display()
            parcelas = list(contrato.parcelas.all())
            pagas = sum(item.status == Parcela.Status.PAGA for item in parcelas)
            if tipo == Contrato.Tipo.VENDA:
                rotulo_valor, valor = 'Valor da venda', contrato.valor_venda
            elif tipo == Contrato.Tipo.JUROS:
                rotulo_valor, valor = 'Valor emprestado', valor_emprestado_somente_juros(contrato)
            else:
                rotulo_valor, valor = 'Valor emprestado', contrato.valor_principal
            topo = [p(f'{nome} · #{contrato.pk:05d}', 'brand'), Spacer(1,5), fields([('Situação', status_label(contrato.status)), ('Início', data_br(contrato.data_inicio)), (rotulo_valor, moeda(valor)), ('Cobrança', moeda(contrato.valor_parcela or contrato.valor_juros_mensal)), ('Parcelas pagas', f'{pagas}/{contrato.qtd_parcelas or len(parcelas)}'), ('Quitação', moeda(valor_quitacao(contrato)))]), Spacer(1,8)]
            if indice == 0:
                topo.insert(0, section(rotulo))
            story.append(KeepTogether(topo))
            rows = []
            for parcela in parcelas:
                numero = str(parcela.numero) if parcela.numero else ('Quitação' if parcela.tipo == Parcela.Tipo.QUITACAO else 'Juros' if parcela.tipo == Parcela.Tipo.JUROS else 'Saldo')
                status = 'atrasada' if parcela.status in ('pendente', 'atrasada') and parcela.data_vencimento < hoje else parcela.status
                rows.append([numero,data_br(parcela.data_vencimento),moeda(parcela.valor),data_br(parcela.data_pagamento),status_label(status)])
            story.extend([grid(['Parcela','Vencimento','Valor','Pagamento','Status'],rows,[.13,.22,.23,.22,.20]),Spacer(1,20)])
    if not contratos:
        story.extend([section('Contratos'),p('Este cliente ainda não possui contratos cadastrados.')])
    return response(story,f'Relatório financeiro - {cliente.nome}',f'relatorio-cliente-{cliente.pk}.pdf')
