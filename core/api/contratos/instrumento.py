"""Instrumento particular de contrato de mútuo (empréstimo de dinheiro) — CC, arts. 586 a 592. Máximo de 2 páginas."""
from decimal import Decimal

from core.models import Contrato
from core.pdf_contrato import LACUNA, Instrumento, _inteiro_extenso, data_br, data_extenso, gerar_pdf, moeda, qualificacao_cliente, qualificacao_empresa, resposta_pdf, t, valor_completo

PERIODO = {'mensal': ('mensais', 'mês'), 'quinzenal': ('quinzenais', 'quinzena'), 'semanal': ('semanais', 'semana')}
TITULO_EXECUTIVO = ('Este instrumento, assinado eletronicamente pelas partes por meio de provedor que confira sua integridade, constitui título executivo extrajudicial, '
                    'dispensadas testemunhas (CPC, art. 784, III e § 4º).')
GERAIS = 'A tolerância quanto ao descumprimento de obrigações não implica novação ou renúncia. '


def _taxa(contrato):
    return f'{Decimal(contrato.taxa_juros_mensal or 0).normalize():f}'.replace('.', ',')


def _vencimento(contrato):
    if contrato.periodicidade == 'semanal' and contrato.dia_semana:
        return f'toda {contrato.get_dia_semana_display().lower()}'
    if contrato.dia_vencimento:
        return f'todo dia {contrato.dia_vencimento} de cada mês'
    return {'semanal': 'semanalmente', 'quinzenal': 'a cada quinze dias'}.get(contrato.periodicidade, 'mensalmente')


def montar_mutuo(contrato: Contrato, nivel=0):
    juros = contrato.tipo == Contrato.Tipo.JUROS
    plural, unidade = PERIODO.get(contrato.periodicidade, PERIODO['mensal'])
    parcelas = list(contrato.parcelas.all())
    valor_juros = Decimal(contrato.valor_juros_mensal or contrato.valor_parcela or 0)
    principal = Decimal(contrato.valor_principal or 0)
    # No "somente juros", o valor de quitação já inclui uma cobrança de juros (mesma regra da tela do cliente).
    emprestado = max(principal - valor_juros, Decimal('0')) if juros else principal
    numero = f'{contrato.pk:05d}'

    doc = Instrumento('INSTRUMENTO PARTICULAR DE CONTRATO DE MÚTUO', f'Contrato nº {numero} · {contrato.get_tipo_display()}', f'Contrato de mútuo nº {numero}', nivel)
    doc.partes(qualificacao_empresa('MUTUANTE'), qualificacao_cliente(contrato.cliente, 'MUTUÁRIO'),
               preambulo='As partes têm entre si justo e acertado este Contrato de Mútuo, regido pelos arts. 586 a 592 do Código Civil e pelas cláusulas seguintes.')

    doc.clausula('Do objeto',
        f'O MUTUANTE empresta ao MUTUÁRIO a quantia de {valor_completo(emprestado)}, entregue em {data_br(contrato.data_inicio)} por ( ) PIX ( ) transferência ( ) dinheiro, '
        'dando o MUTUÁRIO, com a assinatura deste instrumento, plena quitação quanto ao recebimento.')
    if juros:
        primeira = data_br(parcelas[0].data_vencimento) if parcelas else LACUNA
        doc.clausula('Dos encargos e do pagamento',
            f'O MUTUÁRIO pagará remuneração de {valor_completo(valor_juros)} por {unidade} ({_taxa(contrato)}% do valor emprestado), {_vencimento(contrato)}, a partir de {primeira}. '
            'Essas cobranças remuneram o capital e não o amortizam.',
            f'O principal será restituído a qualquer tempo, por iniciativa do MUTUÁRIO ou a pedido do MUTUANTE com 30 (trinta) dias de antecedência, mediante pagamento de '
            f'{valor_completo(principal)}, que já inclui a remuneração do período, encerrando-se as cobranças futuras.')
    else:
        total = Decimal(contrato.valor_parcela or 0) * Decimal(contrato.qtd_parcelas or 0)
        qtd = contrato.qtd_parcelas or 0
        primeira = contrato.data_primeira_parcela or (parcelas[0].data_vencimento if parcelas else None)
        doc.clausula('Dos encargos e do pagamento',
            f'Sobre o valor emprestado incidem juros remuneratórios de {_taxa(contrato)}% por {unidade}, já incluídos nas parcelas, totalizando {valor_completo(total)}, '
            f'pagos em {qtd} ({_inteiro_extenso(qtd)}) parcelas {plural} de {valor_completo(contrato.valor_parcela)}, a primeira em {data_br(primeira)}, conforme o cronograma abaixo.',
            'O MUTUÁRIO pode antecipar pagamentos, com redução proporcional dos juros do período antecipado.')
    doc.clausula('Da comprovação e da mora',
        'Os pagamentos serão feitos por PIX, transferência ou em espécie, valendo o comprovante ou recibo como quitação.',
        'O atraso constitui o MUTUÁRIO em mora independentemente de notificação (CC, art. 397), incidindo multa de 2% (dois por cento), juros de mora de 1% (um por cento) ao mês pro rata die e correção monetária pelo IPCA.')
    doc.clausula('Do vencimento antecipado',
        'Vence antecipadamente toda a dívida, tornando-se exigível o saldo com os encargos, em caso de:',
        incisos=['atraso superior a 30 (trinta) dias em qualquer pagamento;', 'descumprimento de qualquer outra obrigação deste contrato;', 'insolvência do MUTUÁRIO ou protesto que comprometa sua capacidade de pagamento.'])
    doc.clausula('Das disposições gerais',
        GERAIS + TITULO_EXECUTIVO,
        'As partes autorizam comunicações e avisos de cobrança pelo telefone/WhatsApp informado. Os dados pessoais serão tratados apenas para execução deste contrato (Lei nº 13.709/2018).')
    if contrato.observacoes:
        doc.clausula('Das condições especiais', t(contrato.observacoes))
    doc.clausula('Do foro', 'Fica eleito o foro da comarca do domicílio do MUTUÁRIO, com renúncia a qualquer outro.')
    doc.assinaturas(contrato.data_inicio, 'MUTUANTE', 'MUTUÁRIO', contrato.cliente.nome)

    itens = [(p.data_vencimento, p.valor) for p in parcelas]
    resumo = (f'Cobranças {plural} de {moeda(valor_juros)}, {_vencimento(contrato)}, até a restituição do principal de {moeda(principal)}.' if juros
              else f'{len(itens)} parcelas {plural} de {moeda(contrato.valor_parcela)} referentes ao empréstimo de {moeda(emprestado)} de {data_extenso(contrato.data_inicio)}.')
    doc.cronograma('ANEXO – CRONOGRAMA DE PAGAMENTOS', itens, resumo)
    return doc


def contrato_mutuo_bytes(contrato):
    return gerar_pdf(lambda nivel: montar_mutuo(contrato, nivel))


def contrato_mutuo_pdf(contrato):
    return resposta_pdf(contrato_mutuo_bytes(contrato), f'contrato-mutuo-{contrato.pk}.pdf')
