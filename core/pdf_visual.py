"""Identidade visual compartilhada dos relatórios e comprovantes."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from django.conf import settings
from django.http import FileResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image
from reportlab.graphics.shapes import Drawing, Rect, PolyLine, Circle

GREEN = colors.HexColor('#0B6B53')
SOFT = colors.HexColor('#E1F2EB')
INK = colors.HexColor('#0F1A16')
MUTED = colors.HexColor('#55645E')
LINE = colors.HexColor('#E3E8E6')
BG = colors.HexColor('#F7F9F8')
RED = colors.HexColor('#C93A3A')
WIDTH = A4[0] - 88
STYLES = {
    'body': ParagraphStyle('body', fontName='Helvetica', fontSize=9, leading=13, textColor=INK),
    'small': ParagraphStyle('small', fontName='Helvetica', fontSize=8, leading=11, textColor=MUTED),
    'section': ParagraphStyle('section', fontName='Helvetica-Bold', fontSize=11, leading=15, textColor=GREEN, spaceBefore=12, spaceAfter=7, keepWithNext=True),
    'title': ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=25, leading=30, textColor=INK, spaceAfter=8),
    'brand': ParagraphStyle('brand', fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=INK),
    'value': ParagraphStyle('value', fontName='Helvetica-Bold', fontSize=19, leading=25, textColor=GREEN),
}


def p(text, style='body'):
    return Paragraph(escape(str(text or '-')).replace('\n', '<br/>'), STYLES[style])


def section(text):
    return p(text, 'section')


def brand():
    logo = Path(settings.COMPANY_LOGO_PATH)
    if logo.is_file():
        img = Image(str(logo), width=36, height=36, kind='proportional')
        return img
    mark = Drawing(36, 36)
    mark.add(Rect(0, 0, 36, 36, rx=11, ry=11, fillColor=GREEN, strokeColor=None))
    mark.add(PolyLine([9, 12, 15, 18, 20, 14, 27, 22], strokeColor=colors.white, strokeWidth=2.6))
    mark.add(Circle(27, 22, 2.6, fillColor=colors.HexColor('#B9F27C'), strokeColor=None))
    return mark


def header(title, reference):
    company = [p(settings.COMPANY_NAME, 'brand')]
    for value in [settings.COMPANY_LEGAL_NAME, f'CNPJ {settings.COMPANY_CNPJ}' if settings.COMPANY_CNPJ else '', settings.COMPANY_ADDRESS, settings.COMPANY_PHONE]:
        if value:
            company.append(p(value, 'small'))
    row = Table([[brand(), company]], colWidths=[48, WIDTH-48], hAlign='LEFT')
    row.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),10),('LINEBELOW',(0,0),(-1,-1),1,GREEN)]))
    return [row, Spacer(1,12), p(title,'title'), p(f'{reference}  |  Emitido em {timezone.localtime():%d/%m/%Y às %H:%M}', 'small'), Spacer(1,12)]


def metrics(items):
    cells = [[p(label,'small'), Spacer(1,4), p(value,'value')] for label,value in items]
    table = Table([cells], colWidths=[WIDTH/len(cells)]*len(cells), hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),SOFT),('BOX',(0,0),(-1,-1),.6,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEAFTER',(0,0),(-2,-1),.5,LINE),('LEFTPADDING',(0,0),(-1,-1),14),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    return table


def fields(items):
    table = Table([[p(label,'small'),p(value)] for label,value in items], colWidths=[120,WIDTH-120],hAlign='LEFT')
    table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(0,-1),BG),('LINEBELOW',(0,0),(-1,-1),.4,LINE),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    return table


def grid(headers, rows, widths):
    white = ParagraphStyle('table-head', parent=STYLES['small'], fontName='Helvetica-Bold', textColor=colors.white)
    cells = [[Paragraph(escape(str(h)),white) for h in headers]]
    for row in rows:
        cells.append([p(value,'small') for value in row])
    if len(cells)==1:
        cells.append([p('Nenhuma parcela cadastrada','small')]+['']*(len(headers)-1))
    table = Table(cells,colWidths=[WIDTH*w for w in widths],repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),GREEN),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,BG]),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,1),(-1,-1),.35,LINE),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    return table


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(GREEN)
    canvas.rect(0,A4[1]-6,A4[0],6,fill=1,stroke=0)
    canvas.setStrokeColor(LINE)
    canvas.line(44,36,A4[0]-44,36)
    canvas.setFillColor(MUTED)
    canvas.setFont('Helvetica',8)
    name = settings.COMPANY_NAME
    while canvas.stringWidth(name,'Helvetica',8) > WIDTH-80:
        name = name[:-4]+'...'
    canvas.drawString(44,23,name)
    canvas.drawRightString(A4[0]-44,23,f'Página {doc.page}')
    canvas.restoreState()


def response(story, title, filename):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer,pagesize=A4,leftMargin=44,rightMargin=44,topMargin=32,bottomMargin=52,title=title,author=settings.COMPANY_NAME)
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    buffer.seek(0)
    return FileResponse(buffer,as_attachment=True,filename=filename,content_type='application/pdf')


def cards(items):
    rows = []
    for i in range(0, len(items), 2):
        row = []
        for label, value in items[i:i+2]:
            row.append([p(label, 'small'), p(value)])
        rows.append(row + [''] * (2-len(row)))
    table = Table(rows, colWidths=[WIDTH/2]*2, hAlign='LEFT')
    table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,-1),BG),('LINEBELOW',(0,0),(-1,-1),.4,LINE),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    return table
