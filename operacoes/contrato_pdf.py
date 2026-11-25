"""Contrato de locação de motocicleta — CC, arts. 565 a 578; CTB, art. 257, § 7º."""
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer

from core.pdf_contrato import ESTILOS, Instrumento, LACUNA, data_br, moeda, qualificacao_cliente, qualificacao_empresa, t, valor_completo
from .models import Aluguel

PERIODO = {'semanal': ('semanal', 'semana', 7), 'mensal': ('mensal', 'mês', 30)}
ITENS_VISTORIA = ['Lataria / carenagens', 'Pintura', 'Tanque e banco', 'Pneu dianteiro', 'Pneu traseiro', 'Freios', 'Farol, lanternas e setas', 'Retrovisores',
                  'Painel e velocímetro', 'Corrente / relação', 'Bateria e partida', 'Buzina', 'Documento (CRLV)', 'Chave(s) — quantidade', 'Capacete(s) — quantidade',
                  'Quilometragem na entrega', 'Nível de combustível']


def contrato_locacao_pdf(aluguel: Aluguel):
    moto, cliente = aluguel.moto, aluguel.cliente
    periodo, unidade, dias = PERIODO.get(aluguel.periodicidade, PERIODO['mensal'])
    cobrancas = list(aluguel.cobrancas.order_by('vencimento'))
    numero = f'{aluguel.pk:05d}'

    doc = Instrumento('CONTRATO DE LOCAÇÃO DE MOTOCICLETA', f'Contrato nº {numero} · Placa {t(moto.placa)}', f'Contrato de locação de motocicleta nº {numero}')
    doc.partes(
        qualificacao_empresa('LOCADOR'),
        qualificacao_cliente(cliente, 'LOCATÁRIO', f', habilitado(a) na categoria "A", CNH nº {LACUNA}, válida até {LACUNA}'),
        preambulo='As partes acima identificadas têm, entre si, justo e contratado o presente Contrato de Locação de Motocicleta, que se regerá pelos artigos 565 a 578 do Código Civil e pelas cláusulas e condições seguintes.',
    )

    doc.clausula('Do objeto',
        f'O LOCADOR dá em locação ao LOCATÁRIO a motocicleta modelo <b>{t(moto.modelo)}</b>, placa <b>{t(moto.placa)}</b>, '
        f'RENAVAM {LACUNA}, chassi {LACUNA}, ano/modelo {LACUNA}, cor {LACUNA}, de sua propriedade ou posse legítima.',
        'A motocicleta é entregue em perfeitas condições de uso, conservação e funcionamento, com documentação regular, conforme Termo de Vistoria (Anexo II), que integra este contrato e será assinado pelas partes na entrega e na devolução.')
    doc.clausula('Do prazo',
        f'A locação vigorará de <b>{data_br(aluguel.inicio)}</b> a <b>{data_br(aluguel.fim)}</b>, data em que o LOCATÁRIO deverá restituir a motocicleta, independentemente de notificação.',
        'A prorrogação dependerá de novo instrumento ou aditivo escrito. Permanecendo o LOCATÁRIO na posse do veículo após o término sem oposição do LOCADOR, a locação seguirá pelo mesmo aluguel, por prazo indeterminado (Código Civil, art. 574).')
    doc.clausula('Do aluguel e da forma de pagamento',
        f'O LOCATÁRIO pagará ao LOCADOR aluguel {periodo} de {valor_completo(aluguel.valor)}, vencendo-se o primeiro em <b>{data_br(aluguel.primeiro_vencimento)}</b> '
        f'e os demais no mesmo dia de cada {unidade} subsequente, conforme o cronograma do Anexo I.',
        'Os pagamentos serão realizados por PIX, transferência bancária ou em espécie, mediante recibo, que servirá como prova de quitação.',
        'O aluguel remunera exclusivamente o uso da motocicleta. Combustível, pedágios, estacionamentos e demais despesas de uso correm por conta do LOCATÁRIO.')
    doc.clausula('Da garantia',
        f'Como garantia das obrigações deste contrato, o LOCATÁRIO entrega ao LOCADOR caução de R$ {LACUNA} ( ) não se aplica, que será restituída em até 10 (dez) dias após a devolução da motocicleta, '
        'deduzidos eventuais aluguéis em aberto, multas de trânsito, franquias e reparos de danos de responsabilidade do LOCATÁRIO.')
    doc.clausula('Do atraso no pagamento',
        'O atraso no pagamento do aluguel sujeitará o LOCATÁRIO a multa moratória de 2% (dois por cento) e juros de mora de 1% (um por cento) ao mês, calculados pro rata die.',
        f'O atraso superior a {7 if aluguel.periodicidade == "semanal" else 10} dias autoriza o LOCADOR a considerar rescindido este contrato, devendo o LOCATÁRIO restituir imediatamente a motocicleta, '
        'sem prejuízo da cobrança dos valores devidos e das medidas judiciais cabíveis.')
    doc.clausula('Do uso da motocicleta',
        'O LOCATÁRIO se obriga a utilizar a motocicleta com zelo, como se sua fosse (Código Civil, art. 569, I), exclusivamente para fins lícitos e dentro do território nacional, sendo-lhe vedado:',
        'O LOCATÁRIO declara possuir Carteira Nacional de Habilitação válida na categoria "A" e compromete-se a utilizar capacete e demais equipamentos obrigatórios.',
        incisos=['sublocar, ceder, emprestar ou permitir a condução da motocicleta por terceiros sem autorização escrita do LOCADOR;',
                 'utilizá-la em competições, testes, transporte de cargas acima da capacidade ou em desacordo com as normas de trânsito;',
                 'realizar modificações mecânicas, elétricas ou estéticas, ou remover, desligar ou danificar rastreador ou bloqueador eventualmente instalado;',
                 'dar a motocicleta em garantia ou praticar qualquer ato que comprometa a posse e a propriedade do LOCADOR.'])
    doc.clausula('Da manutenção',
        'A manutenção preventiva decorrente do desgaste natural (troca de óleo, revisões periódicas, pneus e relação por desgaste) é de responsabilidade do LOCADOR, cabendo ao LOCATÁRIO comunicar a necessidade com antecedência e apresentar a motocicleta nas datas agendadas.',
        'Os reparos decorrentes de mau uso, negligência, acidente causado pelo LOCATÁRIO ou falta de comunicação de defeitos serão custeados pelo LOCATÁRIO.')
    doc.clausula('Das multas e infrações de trânsito',
        'São de responsabilidade do LOCATÁRIO as multas, pontuações e demais penalidades decorrentes de infrações cometidas durante o período da locação, desde a entrega até a efetiva devolução da motocicleta.',
        'O LOCADOR indicará o LOCATÁRIO como condutor responsável perante o órgão de trânsito, nos termos do art. 257, § 7º, do Código de Trânsito Brasileiro, obrigando-se o LOCATÁRIO a assinar os formulários necessários.',
        'Havendo pagamento de multa pelo LOCADOR, o LOCATÁRIO deverá reembolsá-lo em até 5 (cinco) dias após a comunicação, acompanhada do respectivo comprovante.')
    doc.clausula('Dos sinistros, furto e roubo',
        'Em caso de acidente, furto, roubo ou qualquer dano, o LOCATÁRIO deverá comunicar o LOCADOR imediatamente, em no máximo 24 (vinte e quatro) horas, e registrar boletim de ocorrência.',
        'O LOCATÁRIO responde pelos danos causados à motocicleta e a terceiros durante a locação quando agir com culpa ou dolo, inclusive pela franquia de seguro e pela parcela do prejuízo não coberta.')
    doc.clausula('Da devolução',
        'Ao término ou rescisão da locação, a motocicleta deverá ser devolvida no endereço do LOCADOR, no estado em que foi recebida, ressalvado o desgaste natural do uso, com o mesmo nível de combustível, mediante nova vistoria.',
        'O atraso na devolução sujeitará o LOCATÁRIO ao pagamento do aluguel proporcional aos dias de atraso, sem prejuízo das perdas e danos e das medidas para reaver o bem (Código Civil, art. 575).')
    doc.clausula('Da rescisão',
        'O contrato poderá ser rescindido por qualquer das partes, mediante aviso prévio por escrito de 7 (sete) dias, ficando o LOCATÁRIO obrigado ao pagamento dos aluguéis proporcionais ao período de uso.',
        'O descumprimento de qualquer cláusula autoriza a rescisão imediata pela parte prejudicada, com a devolução imediata da motocicleta.')
    doc.clausula('Das disposições gerais',
        'A tolerância de qualquer das partes quanto ao descumprimento de obrigações não implicará novação, renúncia ou alteração do pactuado.',
        'Este instrumento, assinado pelas partes e por 2 (duas) testemunhas, constitui título executivo extrajudicial, nos termos do art. 784, III, do Código de Processo Civil.',
        'As partes autorizam comunicações, lembretes de vencimento e avisos pelo telefone/WhatsApp informado. Os dados pessoais serão tratados exclusivamente para execução deste contrato, nos termos da Lei nº 13.709/2018 (LGPD).')
    if aluguel.observacoes:
        doc.clausula('Das condições especiais', t(aluguel.observacoes))
    doc.clausula('Do foro',
        'Fica eleito o foro da comarca do domicílio do LOCATÁRIO para dirimir quaisquer controvérsias oriundas deste contrato, com renúncia a qualquer outro, por mais privilegiado que seja.')

    doc.assinaturas(aluguel.inicio, 'LOCADOR', 'LOCATÁRIO', cliente.nome)

    linhas = [[str(i + 1), data_br(c.vencimento), moeda(c.valor), f'Pago em {data_br(c.pago_em)}' if c.pago_em else '', ''] for i, c in enumerate(cobrancas)]
    doc.anexo('ANEXO I – CRONOGRAMA DE ALUGUÉIS', ['Nº', 'Vencimento', 'Valor', 'Situação', 'Visto'], linhas, [1.4 * cm, 3.6 * cm, 3.6 * cm, 4.6 * cm, 3.8 * cm],
              f'Aluguel {periodo} de {moeda(aluguel.valor)} · período de {data_br(aluguel.inicio)} a {data_br(aluguel.fim)}.')
    vistoria = [[item, '', '', ''] for item in ITENS_VISTORIA]
    doc.anexo('ANEXO II – TERMO DE VISTORIA', ['Item', 'Entrega', 'Devolução', 'Observações'], vistoria, [5.4 * cm, 2.6 * cm, 2.6 * cm, 6.4 * cm],
              f'Motocicleta {t(moto.modelo)}, placa {t(moto.placa)}. Marque OK ou descreva avarias. Data da entrega: {data_br(aluguel.inicio)} · Data da devolução: {LACUNA}')
    doc.story.append(Spacer(1, 26))
    doc.story.append(Paragraph('_' * 34 + '&nbsp;' * 10 + '_' * 34, ESTILOS['centro']))
    doc.story.append(Paragraph('LOCADOR' + '&nbsp;' * 62 + 'LOCATÁRIO', ESTILOS['pequeno']))
    return doc.resposta(f'contrato-locacao-{moto.placa}-{aluguel.pk}.pdf')
