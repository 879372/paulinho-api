from io import BytesIO
from pathlib import Path
from django.conf import settings
from django.http import FileResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


GOLD = colors.HexColor('#B9861D')
INK = colors.HexColor('#171912')
MUTED = colors.HexColor('#6E7169')
LINE = colors.HexColor('#E8E7E1')


def moeda(valor):
    valor = valor or 0
    return f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def data_br(data):
    return data.strftime('%d/%m/%Y') if data else '—'


def status_label(status):
    return {'paga': 'Paga', 'atrasada': 'Em atraso', 'pendente': 'Pendente'}.get(status, status.title())


def empresa_linhas():
    linhas = [settings.COMPANY_NAME]
    for valor in [settings.COMPANY_LEGAL_NAME, f'CNPJ: {settings.COMPANY_CNPJ}' if settings.COMPANY_CNPJ else '', f'IE: {settings.COMPANY_IE}' if settings.COMPANY_IE else '', settings.COMPANY_ADDRESS, settings.COMPANY_PHONE]:
        if valor:
            linhas.append(valor)
    return '<br/>'.join(linhas)


def rodape(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(1.8 * cm, 1.45 * cm, A4[0] - 1.8 * cm, 1.45 * cm)
    canvas.setFillColor(MUTED)
    canvas.setFont('Helvetica', 8)
    canvas.drawString(1.8 * cm, 0.95 * cm, f'{settings.COMPANY_NAME} · Documento gerado em {data_br(doc.gerado_em)}')
    canvas.drawRightString(A4[0] - 1.8 * cm, 0.95 * cm, f'Página {doc.page}')
    canvas.restoreState()


def comprovante_pdf(contrato):
    buffer = BytesIO()
    documento = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.8 * cm, leftMargin=1.8 * cm, topMargin=1.7 * cm, bottomMargin=2.1 * cm, title=f'Contrato {contrato.pk}')
    documento.gerado_em = contrato.criado_em.date()
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle('titulo', parent=estilos['Heading1'], fontName='Helvetica-Bold', fontSize=19, leading=23, textColor=INK, spaceAfter=3)
    subtitulo = ParagraphStyle('subtitulo', parent=estilos['Normal'], fontName='Helvetica', fontSize=9, leading=13, textColor=MUTED)
    secao = ParagraphStyle('secao', parent=estilos['Heading2'], fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=GOLD, spaceBefore=16, spaceAfter=7, uppercase=True)
    texto = ParagraphStyle('texto', parent=estilos['Normal'], fontName='Helvetica', fontSize=9.5, leading=14, textColor=INK)
    empresa = ParagraphStyle('empresa', parent=texto, fontSize=8.5, leading=11, textColor=MUTED, alignment=2)
    destaque = ParagraphStyle('destaque', parent=texto, fontName='Helvetica-Bold', fontSize=10, leading=15, textColor=INK, alignment=TA_CENTER)
    story = []

    logo_path = Path(settings.COMPANY_LOGO_PATH)
    logo = Image(str(logo_path), width=2.2 * cm, height=2.2 * cm) if logo_path.is_file() else Spacer(2.2 * cm, 2.2 * cm)
    cabecalho = Table([[logo, [Paragraph('COMPROVANTE DE CONTRATO', titulo), Paragraph(f'Contrato nº {contrato.pk} · Emitido em {data_br(contrato.criado_em.date())}', subtitulo)], Paragraph(empresa_linhas(), empresa)]], colWidths=[2.5 * cm, 8.1 * cm, 6.0 * cm])
    cabecalho.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 10), ('LINEBELOW', (0, 0), (-1, -1), .7, GOLD)]))
    story.append(cabecalho)

    story.append(Paragraph('Cliente', secao))
    dados_cliente = [['Nome', contrato.cliente.nome], ['Telefone', contrato.cliente.telefone], ['CPF', contrato.cliente.cpf or 'Não informado'], ['Endereço', contrato.cliente.endereco or 'Não informado']]
    tabela_cliente = Table(dados_cliente, colWidths=[3.1 * cm, 13.5 * cm])
    tabela_cliente.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F8EFD9')), ('TEXTCOLOR', (0, 0), (0, -1), GOLD), ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTNAME', (1, 0), (1, -1), 'Helvetica'), ('FONTSIZE', (0, 0), (-1, -1), 9), ('GRID', (0, 0), (-1, -1), .4, LINE), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7), ('LEFTPADDING', (0, 0), (-1, -1), 9)]))
    story.append(tabela_cliente)

    story.append(Paragraph('Detalhes da operação', secao))
    if contrato.tipo == 'venda':
        valor_entrada = contrato.valor_entrada or 0
        detalhes = [['Produto', contrato.produto or 'Não informado'], ['Valor da venda', moeda(contrato.valor_venda)], ['Entrada recebida', moeda(valor_entrada)], ['Valor parcelado', moeda((contrato.valor_venda or 0) - valor_entrada)], ['Condição', f'{contrato.qtd_parcelas} parcela(s) de {moeda(contrato.valor_parcela)} · {contrato.periodicidade.title()}'], ['Primeiro vencimento', data_br(contrato.data_primeira_parcela)]]
    else:
        rotulo_valor = 'Valor a receber' if contrato.tipo == 'emprestimo_somente_juros' else 'Valor passado'
        resumo_cobrancas = ['Valor a receber', moeda((contrato.valor_parcela or 0) * (contrato.qtd_parcelas or 0))] if contrato.tipo == 'emprestimo_tradicional' else ['Ciclo', 'Recorrente']
        detalhes = [['Modalidade', contrato.get_tipo_display()], [rotulo_valor, moeda(contrato.valor_principal)], ['Juros informado', f'{contrato.taxa_juros_mensal or 0}% ao mês'], ['Valor da cobrança', moeda(contrato.valor_parcela or contrato.valor_juros_mensal)], resumo_cobrancas, ['Condição', contrato.qtd_parcelas or 'Recorrente até a quitação do valor a receber'], ['Início', data_br(contrato.data_inicio)]]
    tabela_detalhes = Table(detalhes, colWidths=[4.2 * cm, 12.4 * cm])
    tabela_detalhes.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F7F7F4')), ('TEXTCOLOR', (0, 0), (0, -1), MUTED), ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9), ('GRID', (0, 0), (-1, -1), .4, LINE), ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7), ('LEFTPADDING', (0, 0), (-1, -1), 9)]))
    story.append(tabela_detalhes)

    story.append(Paragraph('Cronograma de parcelas', secao))
    linhas_parcelas = [['Nº', 'Vencimento', 'Valor', 'Status']]
    for parcela in contrato.parcelas.all():
        linhas_parcelas.append([str(parcela.numero or '—'), data_br(parcela.data_vencimento), moeda(parcela.valor), status_label(parcela.status)])
    tabela_parcelas = Table(linhas_parcelas, colWidths=[1.4 * cm, 4.6 * cm, 4.8 * cm, 5.8 * cm], repeatRows=1)
    tabela_parcelas.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), INK), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9), ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), .35, LINE), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FAFAF8')]), ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
    story.append(tabela_parcelas)

    story.append(Paragraph('Declaração de ciência e pagamento', secao))
    declaracao = f'O(A) cliente <b>{contrato.cliente.nome}</b>, telefone <b>{contrato.cliente.telefone}</b>, declara ciência das informações desta operação e reconhece a obrigação de efetuar o pagamento dos valores e vencimentos descritos neste documento. O não pagamento nas datas acordadas poderá caracterizar atraso, conforme as condições combinadas entre as partes.'
    story.append(Paragraph(declaracao, texto))
    if contrato.observacoes:
        story.append(Spacer(1, 8))
        story.append(Paragraph(f'<b>Observações:</b> {contrato.observacoes}', texto))
    story.extend([Spacer(1, 25), Paragraph('______________________________________________', destaque), Paragraph('Assinatura do cliente', ParagraphStyle('assinatura', parent=subtitulo, alignment=TA_CENTER)), Spacer(1, 10), Paragraph(f'Local e data: ____________________________________, {data_br(contrato.criado_em.date())}', texto)])
    documento.build(story, onFirstPage=rodape, onLaterPages=rodape)
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f'contrato-{contrato.pk}.pdf', content_type='application/pdf')
