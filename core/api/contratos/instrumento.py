"""Instrumento particular de contrato de mútuo (empréstimo de dinheiro) — CC, arts. 586 a 592."""
from decimal import Decimal

from reportlab.lib.units import cm

from core.models import Contrato
from core.pdf_contrato import _inteiro_extenso, Instrumento, LACUNA, data_br, data_extenso, moeda, qualificacao_cliente, qualificacao_empresa, t, valor_completo

PERIODO = {'mensal': ('mensal', 'mensais', 'mês'), 'quinzenal': ('quinzenal', 'quinzenais', 'quinzena'), 'semanal': ('semanal', 'semanais', 'semana')}


def _taxa(contrato):
    taxa = Decimal(contrato.taxa_juros_mensal or 0).normalize()
    return f'{taxa:f}'.replace('.', ',')


def contrato_mutuo_pdf(contrato: Contrato):
    juros = contrato.tipo == Contrato.Tipo.JUROS
    singular, plural, unidade = PERIODO.get(contrato.periodicidade, PERIODO['mensal'])
    parcelas = list(contrato.parcelas.all())
    valor_juros = Decimal(contrato.valor_juros_mensal or contrato.valor_parcela or 0)
    principal = Decimal(contrato.valor_principal or 0)
    # No "somente juros", o valor de quitação já inclui uma cobrança de juros (mesma regra da tela do cliente).
    emprestado = max(principal - valor_juros, Decimal('0')) if juros else principal
    data_entrega = contrato.data_inicio

    doc = Instrumento('INSTRUMENTO PARTICULAR DE CONTRATO DE MÚTUO', f'Contrato nº {contrato.pk:05d} · {contrato.get_tipo_display()}', f'Contrato de mútuo nº {contrato.pk:05d}')
    doc.partes(
        qualificacao_empresa('MUTUANTE'),
        qualificacao_cliente(contrato.cliente, 'MUTUÁRIO'),
        preambulo='As partes acima identificadas têm, entre si, justo e acertado o presente Contrato de Mútuo, que se regerá pelos artigos 586 a 592 do Código Civil e pelas cláusulas e condições seguintes.',
    )

    doc.clausula('Do objeto',
        f'O presente contrato tem por objeto o empréstimo, pelo MUTUANTE ao MUTUÁRIO, da quantia de {valor_completo(emprestado)}, '
        f'entregue nesta data ({data_br(data_entrega)}) por meio de ( ) PIX  ( ) transferência bancária  ( ) dinheiro em espécie.',
        'O MUTUÁRIO declara ter recebido a quantia acima, dando ao MUTUANTE, com a assinatura deste instrumento, plena quitação quanto à entrega do valor.')

    if juros:
        doc.clausula('Dos encargos e da forma de pagamento',
            f'Pelo empréstimo, o MUTUÁRIO pagará ao MUTUANTE remuneração de {valor_completo(valor_juros)} por {unidade}, correspondente a {_taxa(contrato)}% do valor emprestado, '
            f'com vencimento {_descricao_vencimento(contrato)}, a partir de {data_br(parcelas[0].data_vencimento) if parcelas else LACUNA}.',
            'As cobranças periódicas remuneram o capital e não amortizam o valor emprestado, permanecendo devidas enquanto o principal não for restituído.',
            f'A restituição do principal ocorrerá a qualquer tempo, por iniciativa do MUTUÁRIO ou mediante solicitação do MUTUANTE com antecedência mínima de 30 (trinta) dias, '
            f'pelo pagamento de {valor_completo(principal)}, valor que já inclui a remuneração do período da quitação, encerrando-se as cobranças futuras.')
    else:
        total = Decimal(contrato.valor_parcela or 0) * Decimal(contrato.qtd_parcelas or 0)
        doc.clausula('Dos encargos',
            f'Sobre o valor emprestado incidirão juros remuneratórios de {_taxa(contrato)}% por {unidade}, já incluídos nas parcelas, '
            f'totalizando o valor a restituir de {valor_completo(total)}.')
        doc.clausula('Da forma de pagamento',
            f'O MUTUÁRIO restituirá o valor em {contrato.qtd_parcelas} ({_inteiro_extenso(contrato.qtd_parcelas or 0)}) parcelas {plural} e sucessivas de {valor_completo(contrato.valor_parcela)} cada, '
            f'vencendo-se a primeira em {data_br(contrato.data_primeira_parcela or (parcelas[0].data_vencimento if parcelas else None))} e as demais conforme o cronograma do Anexo I.',
            'É facultado ao MUTUÁRIO antecipar o pagamento, total ou parcial, com redução proporcional dos juros remuneratórios correspondentes ao período antecipado.')

    doc.clausula('Do local e da comprovação dos pagamentos',
        'Os pagamentos serão realizados por PIX, transferência bancária ou em espécie, mediante recibo. O comprovante de transferência ou o recibo assinado pelo MUTUANTE servirá como prova de quitação da respectiva parcela.')
    doc.clausula('Da mora',
        'O não pagamento de qualquer valor na data de vencimento constituirá o MUTUÁRIO em mora, independentemente de notificação (Código Civil, art. 397), '
        'sujeitando o débito a multa moratória de 2% (dois por cento), juros de mora de 1% (um por cento) ao mês, calculados pro rata die, e correção monetária pelo IPCA/IBGE, até o efetivo pagamento.')
    doc.clausula('Do vencimento antecipado',
        'Considerar-se-á antecipadamente vencida a totalidade da dívida, tornando-se imediatamente exigível o saldo devedor com os encargos previstos, nas seguintes hipóteses:',
        incisos=['atraso superior a 30 (trinta) dias no pagamento de qualquer parcela ou cobrança periódica;',
                 'descumprimento de qualquer outra obrigação assumida neste contrato;',
                 'insolvência civil do MUTUÁRIO ou protesto de títulos contra ele que comprometa sua capacidade de pagamento.'])
    doc.clausula('Das disposições gerais',
        'A tolerância de qualquer das partes quanto ao descumprimento de obrigações não implicará novação, renúncia ou alteração do pactuado.',
        'Este instrumento, assinado pelo MUTUÁRIO e por 2 (duas) testemunhas, constitui título executivo extrajudicial, nos termos do art. 784, III, do Código de Processo Civil.',
        'As partes autorizam o envio de comunicações, lembretes de vencimento e avisos de cobrança pelo telefone/WhatsApp informado na qualificação, comprometendo-se a manter seus dados atualizados.',
        'Os dados pessoais aqui informados serão tratados exclusivamente para execução deste contrato e exercício regular de direitos, nos termos da Lei nº 13.709/2018 (LGPD).')
    if contrato.observacoes:
        doc.clausula('Das condições especiais', t(contrato.observacoes))
    doc.clausula('Do foro',
        'Fica eleito o foro da comarca do domicílio do MUTUÁRIO para dirimir quaisquer controvérsias oriundas deste contrato, com renúncia a qualquer outro, por mais privilegiado que seja.')

    doc.assinaturas(data_entrega, 'MUTUANTE', 'MUTUÁRIO', contrato.cliente.nome)

    linhas = [[str(p.numero or i + 1), data_br(p.data_vencimento), 'Juros do período' if p.tipo == 'juros_mensal' else ('Quitação do principal' if p.tipo == 'quitacao_principal' else 'Parcela'), moeda(p.valor), '']
              for i, p in enumerate(parcelas)]
    observacao = (f'Cobranças {plural} geradas até esta data. Novas cobranças de {moeda(valor_juros)} serão devidas {_descricao_vencimento(contrato)} até a restituição do principal ({moeda(principal)}).'
                  if juros else f'Cronograma de restituição do empréstimo de {moeda(emprestado)} iniciado em {data_extenso(data_entrega)}.')
    doc.anexo('ANEXO I – CRONOGRAMA DE PAGAMENTOS', ['Nº', 'Vencimento', 'Descrição', 'Valor', 'Visto'], linhas, [1.4 * cm, 3.2 * cm, 5.6 * cm, 3.4 * cm, 3.4 * cm], observacao)
    return doc.resposta(f'contrato-mutuo-{contrato.pk}.pdf')


def _descricao_vencimento(contrato):
    if contrato.periodicidade == 'semanal' and contrato.dia_semana:
        return f'toda {contrato.get_dia_semana_display().lower()}'
    if contrato.dia_vencimento:
        return f'todo dia {contrato.dia_vencimento} de cada mês'
    return {'semanal': 'semanalmente', 'quinzenal': 'a cada quinze dias'}.get(contrato.periodicidade, 'mensalmente')
