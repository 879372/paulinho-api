from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.http import FileResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


INK = colors.HexColor('#20231C')
GOLD = colors.HexColor('#B58425')
GOLD_SOFT = colors.HexColor('#F8EFD9')
MUTED = colors.HexColor('#73766E')
LINE = colors.HexColor('#DDDCD5')


def moeda(valor):
    return f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def data_br(valor):
    return valor.strftime('%d/%m/%Y')


def montar_pdf(dados):
    buffer = BytesIO()
    documento = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.8 * cm, leftMargin=1.8 * cm, topMargin=1.7 * cm, bottomMargin=1.7 * cm, title='Comprovante de compra')
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle('titulo_nota', parent=estilos['Heading1'], fontName='Helvetica-Bold', fontSize=20, leading=24, textColor=INK, spaceAfter=4)
    subtitulo = ParagraphStyle('subtitulo_nota', parent=estilos['Normal'], fontSize=9, leading=13, textColor=MUTED)
    secao = ParagraphStyle('secao_nota', parent=estilos['Heading2'], fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=GOLD, spaceBefore=17, spaceAfter=7)
    texto = ParagraphStyle('texto_nota', parent=estilos['Normal'], fontSize=9.5, leading=15, textColor=INK)
    direita = ParagraphStyle('direita_nota', parent=subtitulo, alignment=TA_RIGHT)
    centro = ParagraphStyle('centro_nota', parent=subtitulo, alignment=TA_CENTER)
    story = []

    logo_path = Path(settings.COMPANY_LOGO_PATH)
    logo = Image(str(logo_path), width=2.1 * cm, height=2.1 * cm) if logo_path.is_file() else Spacer(2.1 * cm, 2.1 * cm)
    loja = [
        Paragraph(f'<b>{settings.COMPANY_NAME}</b>', texto),
        Paragraph(f'CNPJ: {settings.COMPANY_CNPJ or "não informado"}', subtitulo),
        Paragraph(f'Telefone: {settings.COMPANY_PHONE or "não informado"}', subtitulo),
    ]
    emissao = [Paragraph('<b>COMPROVANTE DE COMPRA</b>', direita), Paragraph(f'Emitido em {data_br(dados["data_compra"])}', direita)]
    cabecalho = Table([[logo, loja, emissao]], colWidths=[2.5 * cm, 8.2 * cm, 5.9 * cm])
    cabecalho.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 12), ('LINEBELOW', (0, 0), (-1, -1), 1, GOLD)]))
    story.extend([cabecalho, Spacer(1, 18), Paragraph('COMPROVANTE DE COMPRA', titulo), Paragraph('Documento de confirmação da compra e das condições de garantia do produto.', subtitulo)])

    story.append(Paragraph('Dados da compra', secao))
    forma = dict([('pix', 'PIX'), ('dinheiro', 'Dinheiro'), ('cartao_credito', 'Cartão de crédito'), ('cartao_debito', 'Cartão de débito'), ('transferencia', 'Transferência')])[dados['forma_pagamento']]
    detalhes = [
        ['Cliente', dados['cliente_nome']],
        ['Produto', dados['produto']],
        ['Valor do produto', moeda(dados['valor_produto'])],
        ['Forma de pagamento', forma],
        ['Data da compra', data_br(dados['data_compra'])],
        ['Garantia', dados['garantia']],
    ]
    tabela = Table(detalhes, colWidths=[4.3 * cm, 12.3 * cm])
    tabela.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, -1), GOLD_SOFT), ('TEXTCOLOR', (0, 0), (0, -1), GOLD), ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTNAME', (1, 0), (1, -1), 'Helvetica'), ('FONTSIZE', (0, 0), (-1, -1), 9.5), ('GRID', (0, 0), (-1, -1), .5, LINE), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 9), ('BOTTOMPADDING', (0, 0), (-1, -1), 9), ('LEFTPADDING', (0, 0), (-1, -1), 10)]))
    story.append(tabela)

    story.append(Paragraph('Declaração de compra e garantia', secao))
    declaracao = f'O(A) cliente <b>{dados["cliente_nome"]}</b> declara estar ciente da compra do produto <b>{dados["produto"]}</b>, realizada em <b>{data_br(dados["data_compra"])}</b>, pelo valor de <b>{moeda(dados["valor_produto"])}</b>. A garantia informada para esta compra é de <b>{dados["garantia"]}</b>, contada a partir da data da compra, para defeitos cobertos pelas condições legais e comerciais aplicáveis.'
    story.append(Paragraph(declaracao, texto))
    story.append(Spacer(1, 9))
    story.append(Paragraph('A garantia não cobre danos decorrentes de mau uso, quedas, contato com líquidos, violação do produto, instalação inadequada ou intervenção realizada por terceiros não autorizados.', texto))

    story.extend([Spacer(1, 38), Paragraph('______________________________________________', centro), Paragraph(dados['cliente_nome'], centro), Paragraph('Ciência do cliente', centro), Spacer(1, 22), Paragraph(f'{settings.COMPANY_NAME}', centro)])
    documento.build(story)
    buffer.seek(0)
    return buffer


def comprovante_compra_pdf(dados):
    buffer = montar_pdf(dados)
    return FileResponse(buffer, as_attachment=True, filename='comprovante-compra.pdf', content_type='application/pdf')
