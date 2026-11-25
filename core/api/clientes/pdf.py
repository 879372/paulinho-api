from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import FileResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.models import Contrato, Parcela


GOLD = colors.HexColor('#B9861D')
GOLD_SOFT = colors.HexColor('#FFF8E8')
INK = colors.HexColor('#171912')
MUTED = colors.HexColor('#6E7169')
LINE = colors.HexColor('#E8E7E1')
GREEN = colors.HexColor('#24754A')


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
        Parcela.Status.PENDENTE: 'Pendente', Parcela.Status.ATRASADA: 'Em atraso',
    }.get(status, status.title())


def valor_quitacao(contrato):
    if contrato.status in [Contrato.Status.QUITADO, Contrato.Status.CANCELADO, Contrato.Status.RENEGOCIADO]:
        return Decimal('0')
    if contrato.tipo == Contrato.Tipo.JUROS:
        return contrato.valor_principal or Decimal('0')
    return sum((parcela.valor for parcela in contrato.parcelas.all() if parcela.status != Parcela.Status.PAGA), Decimal('0'))


def valor_emprestado_somente_juros(contrato):
    valor_a_receber = contrato.valor_principal or Decimal('0')
    juros = contrato.valor_juros_mensal or contrato.valor_parcela or Decimal('0')
    return max(valor_a_receber - juros, Decimal('0'))


def rodape(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(1.7 * cm, 1.35 * cm, A4[0] - 1.7 * cm, 1.35 * cm)
    canvas.setFillColor(MUTED)
    canvas.setFont('Helvetica', 8)
    canvas.drawString(1.7 * cm, .88 * cm, f'{settings.COMPANY_NAME} - relatório atualizado em {data_br(date.today())}')
    canvas.drawRightString(A4[0] - 1.7 * cm, .88 * cm, f'Página {doc.page}')
    canvas.restoreState()


def relatorio_cliente_pdf(cliente):
    contratos = list(cliente.contratos.all())
    total_quitacao = sum((valor_quitacao(contrato) for contrato in contratos), Decimal('0'))
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.7 * cm, leftMargin=1.7 * cm, topMargin=1.5 * cm, bottomMargin=1.9 * cm, title=f'Relatório financeiro - {cliente.nome}')
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle('rel_titulo', parent=estilos['Heading1'], fontName='Helvetica-Bold', fontSize=18, leading=22, textColor=INK)
    normal = ParagraphStyle('rel_normal', parent=estilos['Normal'], fontSize=8.8, leading=12.5, textColor=INK)
    pequeno = ParagraphStyle('rel_pequeno', parent=normal, fontSize=8, textColor=MUTED)
    direita = ParagraphStyle('rel_direita', parent=pequeno, alignment=TA_RIGHT)
    secao = ParagraphStyle('rel_secao', parent=estilos['Heading2'], fontName='Helvetica-Bold', fontSize=11, leading=14, textColor=GOLD, spaceBefore=15, spaceAfter=7)
    contrato_titulo = ParagraphStyle('rel_contrato', parent=normal, fontName='Helvetica-Bold', fontSize=10, leading=14)
    story = []

    logo_path = Path(settings.COMPANY_LOGO_PATH)
    logo = Image(str(logo_path), width=1.8 * cm, height=1.8 * cm) if logo_path.is_file() else Spacer(1.8 * cm, 1.8 * cm)
    empresa = [Paragraph(f'<b>{escape(settings.COMPANY_NAME)}</b>', normal), Paragraph('RELATÓRIO FINANCEIRO DO CLIENTE', pequeno)]
    emissao = [Paragraph(f'<b>Atualizado em {data_br(date.today())}</b>', direita), Paragraph(f'{len(contratos)} contrato(s)', direita)]
    cabecalho = Table([[logo, empresa, emissao]], colWidths=[2.2 * cm, 9.2 * cm, 5.2 * cm])
    cabecalho.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 10), ('LINEBELOW', (0, 0), (-1, -1), 1, GOLD)]))
    story.extend([cabecalho, Spacer(1, 16), Paragraph(escape(cliente.nome), titulo), Paragraph(f'Telefone: {escape(cliente.telefone)} &nbsp;&nbsp; CPF: {escape(cliente.cpf or "Não informado")}', pequeno), Spacer(1, 13)])

    resumo = Table([
        [Paragraph('<b>CONTRATOS</b>', pequeno), Paragraph('<b>TOTAL PARA QUITAÇÃO</b>', pequeno)],
        [Paragraph(f'<b>{len(contratos)}</b>', contrato_titulo), Paragraph(f'<b>{moeda(total_quitacao)}</b>', contrato_titulo)],
    ], colWidths=[8.3 * cm, 8.3 * cm])
    resumo.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), GOLD_SOFT), ('BOX', (0, 0), (-1, -1), .7, GOLD), ('INNERGRID', (0, 0), (-1, -1), .4, LINE), ('TEXTCOLOR', (0, 0), (-1, 0), GOLD), ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7), ('LEFTPADDING', (0, 0), (-1, -1), 10)]))
    story.append(resumo)

    grupos = [(Contrato.Tipo.VENDA, 'PRODUTOS'), (Contrato.Tipo.TRADICIONAL, 'EMPRÉSTIMOS'), (Contrato.Tipo.JUROS, 'EMPRÉSTIMOS - SOMENTE JUROS')]
    primeiro_grupo = True
    for tipo, rotulo in grupos:
        itens = [contrato for contrato in contratos if contrato.tipo == tipo]
        if not itens:
            continue
        if not primeiro_grupo:
            story.append(PageBreak())
        primeiro_grupo = False
        story.append(Paragraph(rotulo, secao))
        for contrato in itens:
            pagas = sum(1 for parcela in contrato.parcelas.all() if parcela.status == Parcela.Status.PAGA)
            if contrato.tipo == Contrato.Tipo.VENDA:
                nome = contrato.produto or 'Produto sem descrição'
                detalhes = f'{pagas}/{contrato.qtd_parcelas or len(contrato.parcelas.all())} parcelas | Parcela {moeda(contrato.valor_parcela)} | Quitação {moeda(valor_quitacao(contrato))}'
                valor_base = ('Valor da venda', moeda(contrato.valor_venda))
            elif contrato.tipo == Contrato.Tipo.TRADICIONAL:
                nome = f'Empréstimo #{contrato.pk}'
                detalhes = f'{pagas}/{contrato.qtd_parcelas or len(contrato.parcelas.all())} parcelas | Parcela {moeda(contrato.valor_parcela)} | Quitação {moeda(valor_quitacao(contrato))}'
                valor_base = ('Valor emprestado', moeda(contrato.valor_principal))
            else:
                nome = f'Empréstimo somente juros #{contrato.pk}'
                detalhes = f'Juros {moeda(contrato.valor_juros_mensal or contrato.valor_parcela)} | Quitação {moeda(valor_quitacao(contrato))}'
                valor_base = ('Valor emprestado', moeda(valor_emprestado_somente_juros(contrato)))

            dados = Table([
                [Paragraph(f'<b>{escape(nome)}</b>', contrato_titulo), Paragraph(f'<b>{status_label(contrato.status)}</b>', direita)],
                [Paragraph(f'Início: {data_br(contrato.data_inicio)}', pequeno), Paragraph(f'{escape(valor_base[0])}: {valor_base[1]}', direita)],
                [Paragraph(escape(detalhes), normal), ''],
            ], colWidths=[12.1 * cm, 4.5 * cm])
            dados.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FAFAF8')), ('BOX', (0, 0), (-1, -1), .5, LINE), ('SPAN', (0, 2), (1, 2)), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6), ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8)]))
            parcelas = [['Nº', 'Vencimento', 'Valor', 'Pagamento', 'Status']]
            for parcela in contrato.parcelas.all():
                numero = str(parcela.numero) if parcela.numero else ('Quitação' if parcela.tipo == Parcela.Tipo.QUITACAO else 'Juros')
                parcelas.append([numero, data_br(parcela.data_vencimento), moeda(parcela.valor), data_br(parcela.data_pagamento), status_label(parcela.status)])
            if len(parcelas) == 1:
                parcelas.append(['-', '-', '-', '-', 'Nenhuma cobrança'])
            tabela_parcelas = Table(parcelas, colWidths=[2.0 * cm, 3.5 * cm, 3.6 * cm, 3.5 * cm, 4.0 * cm], repeatRows=1)
            tabela_parcelas.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), INK), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8), ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), .35, LINE), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FAFAF8')]), ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
            story.extend([KeepTogether([dados, Spacer(1, 5)]), tabela_parcelas, Spacer(1, 12)])

    if not contratos:
        story.extend([Spacer(1, 18), Paragraph('Este cliente ainda não possui contratos cadastrados.', normal)])
    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f'relatorio-cliente-{cliente.pk}.pdf', content_type='application/pdf')
