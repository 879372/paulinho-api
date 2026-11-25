"""Contrato de locação de motocicleta — CC, arts. 565 a 578; CTB, art. 257, § 7º. Máximo de 2 páginas."""
from core.pdf_contrato import LACUNA, Instrumento, data_br, gerar_pdf, moeda, qualificacao_cliente, qualificacao_empresa, resposta_pdf, t, valor_completo
from core.api.contratos.instrumento import GERAIS, TITULO_EXECUTIVO
from .models import Aluguel

PERIODO = {'semanal': ('semanal', 'semana', 'semanais'), 'mensal': ('mensal', 'mês', 'mensais')}
ITENS_VISTORIA = ['Lataria e carenagens', 'Pintura e tanque', 'Banco', 'Pneu dianteiro', 'Pneu traseiro', 'Freios', 'Farol, lanternas e setas', 'Retrovisores', 'Painel',
                  'Corrente / relação', 'Bateria e partida', 'Documento (CRLV)', 'Chaves (qtd.)', 'Capacete (qtd.)', 'Quilometragem', 'Combustível']


def montar_locacao(aluguel: Aluguel, nivel=0):
    moto, cliente = aluguel.moto, aluguel.cliente
    periodo, unidade, plural = PERIODO.get(aluguel.periodicidade, PERIODO['mensal'])
    numero = f'{aluguel.pk:05d}'
    tolerancia = 7 if aluguel.periodicidade == 'semanal' else 10

    doc = Instrumento('CONTRATO DE LOCAÇÃO DE MOTOCICLETA', f'Contrato nº {numero} · Placa {t(moto.placa)}', f'Contrato de locação de motocicleta nº {numero}', nivel)
    doc.partes(qualificacao_empresa('LOCADOR'), qualificacao_cliente(cliente, 'LOCATÁRIO', f', CNH categoria "A" nº {LACUNA}'),
               preambulo='As partes têm entre si justo e contratado esta Locação de Motocicleta, regida pelos arts. 565 a 578 do Código Civil e pelas cláusulas seguintes.')

    doc.clausula('Do objeto e do prazo',
        f'O LOCADOR loca ao LOCATÁRIO a motocicleta <b>{t(moto.modelo)}</b>, placa <b>{t(moto.placa)}</b>, RENAVAM {LACUNA}, ano/cor {LACUNA}, '
        f'de <b>{data_br(aluguel.inicio)}</b> a <b>{data_br(aluguel.fim)}</b>, entregue em perfeito estado conforme a vistoria abaixo.',
        'A prorrogação depende de aditivo escrito; permanecendo o LOCATÁRIO com a moto após o término sem oposição, a locação segue pelo mesmo aluguel por prazo indeterminado (CC, art. 574).')
    caucao = (f'Caução: R$ {LACUNA} ( ) não se aplica.' if aluguel.valor_caucao is None else 'Não foi estipulada caução para esta locação.' if aluguel.valor_caucao == 0 else f'Caução ajustada em {valor_completo(aluguel.valor_caucao)}, restituída em até 10 (dez) dias após a devolução, deduzidos débitos, multas, franquias e reparos de responsabilidade do LOCATÁRIO.')
    doc.clausula('Do aluguel e da garantia',
        f'O aluguel {periodo} é de {valor_completo(aluguel.valor)}, com primeiro vencimento em <b>{data_br(aluguel.primeiro_vencimento)}</b> e os demais a cada {unidade}, '
        'pago por PIX, transferência ou em espécie, valendo o comprovante como quitação. Combustível, pedágios e estacionamentos correm por conta do LOCATÁRIO.',
        caucao)
    doc.clausula('Do atraso',
        f'O atraso sujeita o LOCATÁRIO a multa de 2% (dois por cento) e juros de 1% (um por cento) ao mês pro rata die. Atraso superior a {tolerancia} dias autoriza a rescisão, '
        'devendo a moto ser devolvida imediatamente, sem prejuízo da cobrança e das medidas judiciais cabíveis.')
    doc.clausula('Do uso',
        'O LOCATÁRIO, habilitado na categoria "A", usará a moto com zelo (CC, art. 569), para fins lícitos, com capacete e equipamentos obrigatórios, sendo-lhe vedado:',
        incisos=['sublocar, ceder ou emprestar a moto, ou permitir que terceiros a conduzam;',
                 'usá-la em competições ou em desacordo com as normas de trânsito;',
                 'modificá-la ou remover/desligar rastreador ou bloqueador instalado.'])
    doc.clausula('Da manutenção, multas e sinistros',
        'A manutenção por desgaste natural (óleo, revisões, pneus e relação) cabe ao LOCADOR, devendo o LOCATÁRIO comunicar a necessidade e apresentar a moto; reparos por mau uso ou culpa cabem ao LOCATÁRIO.',
        'Multas e pontuações do período da locação são do LOCATÁRIO, que será indicado como condutor (CTB, art. 257, § 7º) e reembolsará multas pagas pelo LOCADOR em até 5 (cinco) dias.',
        'Acidente, furto ou roubo devem ser comunicados em até 24 horas, com boletim de ocorrência; o LOCATÁRIO responde pelos danos causados por culpa ou dolo, inclusive franquia de seguro.')
    doc.clausula('Da devolução e da rescisão',
        'A moto será devolvida no endereço do LOCADOR no estado em que foi recebida, salvo desgaste natural; o atraso na devolução gera aluguel proporcional por dia, além de perdas e danos (CC, art. 575).',
        'Qualquer parte pode rescindir com aviso escrito de 7 (sete) dias; o descumprimento de cláusula autoriza a rescisão imediata.')
    doc.clausula('Das disposições gerais',
        GERAIS + TITULO_EXECUTIVO,
        'As partes autorizam comunicações e avisos pelo telefone/WhatsApp informado. Os dados pessoais serão tratados apenas para execução deste contrato (Lei nº 13.709/2018).')
    if aluguel.observacoes:
        doc.clausula('Das condições especiais', t(aluguel.observacoes))
    doc.clausula('Do foro', 'Fica eleito o foro da comarca do domicílio do LOCATÁRIO, com renúncia a qualquer outro.')
    doc.assinaturas(aluguel.inicio, 'LOCADOR', 'LOCATÁRIO', cliente.nome)

    itens = [(c.vencimento, c.valor) for c in aluguel.cobrancas.filter(transferida_para__isnull=True).order_by('vencimento')]
    doc.cronograma('ANEXO I – CRONOGRAMA DE ALUGUÉIS', itens, f'{len(itens)} aluguéis {plural} de {moeda(aluguel.valor)}, de {data_br(aluguel.inicio)} a {data_br(aluguel.fim)}.')
    doc.checklist('ANEXO II – VISTORIA', ITENS_VISTORIA, 'Marque OK ou anote a avaria na entrega e na devolução.')
    return doc


def contrato_locacao_bytes(aluguel):
    return gerar_pdf(lambda nivel: montar_locacao(aluguel, nivel))


def contrato_locacao_pdf(aluguel):
    return resposta_pdf(contrato_locacao_bytes(aluguel), f'contrato-locacao-{aluguel.moto.placa}-{aluguel.pk}.pdf')
