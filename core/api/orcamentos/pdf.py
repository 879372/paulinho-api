from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import FileResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.api.comprovantes.pdf import GOLD, GOLD_SOFT, INK, LINE, MUTED, data_br, moeda


TIPOS = {
    'servico': 'SERVIÇO',
    'produto': 'PRODUTO',
    'emprestimo_tradicional': 'EMPRÉSTIMO TRADICIONAL',
    'emprestimo_somente_juros': 'EMPRÉSTIMO SOMENTE JUROS',
}


def percentual(valor):
    return format(valor, 'f').rstrip('0').rstrip('.').replace('.', ',')


def total_item(item):
    quantidade = item.get('quantidade', 1)
    if item['tipo'] == 'servico':
        return item['valor_unitario'] * quantidade
    if item['tipo'] == 'produto':
        if item['forma_proposta'] == 'avista':
            return item['valor_avista'] * quantidade
        return item.get('valor_entrada', 0) + item['valor_parcela'] * item['qtd_parcelas'] * quantidade
    if item['tipo'] == 'emprestimo_tradicional':
        return item['valor_parcela'] * item['qtd_parcelas']
    return item['valor_quitacao']


def linhas_item(item):
    tipo = item['tipo']
    if tipo == 'servico':
        linhas = [('Descrição', item['descricao']), ('Quantidade', str(item['quantidade'])), ('Valor unitário', moeda(item['valor_unitario']))]
        if item.get('garantia'):
            linhas.append(('Garantia', item['garantia']))
        return linhas
    if tipo == 'produto':
        linhas = [('Produto', item['descricao']), ('Quantidade', str(item['quantidade']))]
        if item['forma_proposta'] == 'avista':
            linhas.append(('Condição', f'À vista por {moeda(item["valor_avista"])} cada'))
        else:
            linhas.append(('Condição', f'{item["qtd_parcelas"]}x de {moeda(item["valor_parcela"])} por unidade'))
            if item.get('valor_entrada'):
                linhas.append(('Entrada', moeda(item['valor_entrada'])))
        if item.get('garantia'):
            linhas.append(('Garantia', item['garantia']))
        return linhas
    if tipo == 'emprestimo_tradicional':
        return [('Valor emprestado', moeda(item['valor_emprestado'])), ('Juros informado', f'{percentual(item["taxa_juros_mensal"])}% ao mês'), ('Condição', f'{item["qtd_parcelas"]}x de {moeda(item["valor_parcela"])}')]
    linhas = [('Valor emprestado', moeda(item['valor_emprestado'])), ('Juros mensais', f'{moeda(item["juros_mensal"])} por mês até a quitação'), ('Valor de quitação', moeda(item['valor_quitacao']))]
    if item.get('taxa_juros_mensal') is not None:
        linhas.insert(2, ('Taxa informada', f'{percentual(item["taxa_juros_mensal"])}% ao mês'))
    return linhas


def montar_pdf(dados):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.8 * cm, leftMargin=1.8 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm, title='Orçamento')
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle('titulo_orcamento', parent=estilos['Heading1'], fontName='Helvetica-Bold', fontSize=20, leading=24, textColor=INK)
    normal = ParagraphStyle('normal_orcamento', parent=estilos['Normal'], fontSize=9.2, leading=14, textColor=INK)
    pequeno = ParagraphStyle('pequeno_orcamento', parent=normal, fontSize=8.5, textColor=MUTED)
    direita = ParagraphStyle('direita_orcamento', parent=pequeno, alignment=TA_RIGHT)
    centro = ParagraphStyle('centro_orcamento', parent=pequeno, alignment=TA_CENTER)
    item_titulo = ParagraphStyle('item_titulo', parent=normal, fontName='Helvetica-Bold', fontSize=10, textColor=GOLD)
    story = []

    logo_path = Path(settings.COMPANY_LOGO_PATH)
    logo = Image(str(logo_path), width=2 * cm, height=2 * cm) if logo_path.is_file() else Spacer(2 * cm, 2 * cm)
    loja = [Paragraph(f'<b>{escape(settings.COMPANY_NAME)}</b>', normal), Paragraph(f'CNPJ: {settings.COMPANY_CNPJ or "não informado"}', pequeno), Paragraph(f'Telefone: {settings.COMPANY_PHONE or "não informado"}', pequeno)]
    emissao = [Paragraph('<b>ORÇAMENTO</b>', direita), Paragraph(f'Emissão: {data_br(dados["data_emissao"])}', direita), Paragraph(f'Válido até: {data_br(dados["validade"])}', direita)]
    cabecalho = Table([[logo, loja, emissao]], colWidths=[2.4 * cm, 8.3 * cm, 5.9 * cm])
    cabecalho.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 11), ('LINEBELOW', (0, 0), (-1, -1), 1, GOLD)]))
    story.extend([cabecalho, Spacer(1, 17), Paragraph('ORÇAMENTO', titulo), Paragraph(f'Proposta preparada para <b>{escape(dados["cliente_nome"])}</b>.', normal), Spacer(1, 15)])

    for indice, item in enumerate(dados['itens'], 1):
        linhas = [[Paragraph(f'<b>{escape(rotulo)}</b>', pequeno), Paragraph(escape(str(valor)), normal)] for rotulo, valor in linhas_item(item)]
        linhas.append([Paragraph('<b>TOTAL DO ITEM</b>', item_titulo), Paragraph(f'<b>{moeda(total_item(item))}</b>', item_titulo)])
        tabela = Table(linhas, colWidths=[4.2 * cm, 12.4 * cm])
        tabela.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, -2), GOLD_SOFT), ('GRID', (0, 0), (-1, -2), .4, LINE), ('BOX', (0, -1), (-1, -1), .8, GOLD), ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FFFCF5')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7), ('LEFTPADDING', (0, 0), (-1, -1), 9)]))
        bloco = [Paragraph(f'ITEM {indice} · {TIPOS[item["tipo"]]}', item_titulo), Spacer(1, 5), tabela, Spacer(1, 13)]
        story.append(KeepTogether(bloco))

    if dados.get('observacoes'):
        story.extend([Paragraph('<b>OBSERVAÇÕES</b>', item_titulo), Spacer(1, 5), Paragraph(escape(dados['observacoes']).replace('\n', '<br/>'), normal), Spacer(1, 13)])
    story.extend([Paragraph('Este documento é uma proposta comercial e não comprova pagamento, entrega de produto, execução de serviço ou liberação de empréstimo.', pequeno), Spacer(1, 28), Paragraph('______________________________________________', centro), Paragraph(escape(dados['cliente_nome']), centro), Paragraph('Aceite do cliente', centro)])
    doc.build(story)
    buffer.seek(0)
    return buffer


def orcamento_pdf(dados):
    return FileResponse(montar_pdf(dados), as_attachment=True, filename='orcamento.pdf', content_type='application/pdf')
