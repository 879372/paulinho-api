"""Base compartilhada dos instrumentos contratuais em PDF (mútuo e locação de moto).

Estrutura inspirada nos modelos usuais de mercado: qualificação das partes,
cláusulas numeradas, assinaturas com duas testemunhas (CPC, art. 784, III) e anexos.
"""
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import FileResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PRIMARY = colors.HexColor('#0B6B53')
INK = colors.HexColor('#0F1A16')
MUTED = colors.HexColor('#55645E')
LINE = colors.HexColor('#D5DDDA')
SOFT = colors.HexColor('#EEF5F2')
LACUNA = '_' * 22

MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']

ESTILOS = {
    'titulo': ParagraphStyle('titulo', fontName='Helvetica-Bold', fontSize=13.5, leading=18, alignment=TA_CENTER, textColor=INK, spaceAfter=2),
    'subtitulo': ParagraphStyle('subtitulo', fontName='Helvetica', fontSize=8.5, leading=12, alignment=TA_CENTER, textColor=MUTED, spaceAfter=14),
    'parte': ParagraphStyle('parte', fontName='Helvetica', fontSize=9.3, leading=13.6, alignment=TA_JUSTIFY, textColor=INK, spaceAfter=7),
    'clausula': ParagraphStyle('clausula', fontName='Helvetica-Bold', fontSize=9.5, leading=13, textColor=PRIMARY, spaceBefore=10, spaceAfter=4),
    'texto': ParagraphStyle('texto', fontName='Helvetica', fontSize=9.3, leading=13.6, alignment=TA_JUSTIFY, textColor=INK, spaceAfter=4),
    'inciso': ParagraphStyle('inciso', fontName='Helvetica', fontSize=9.3, leading=13.6, alignment=TA_JUSTIFY, textColor=INK, leftIndent=14, spaceAfter=3),
    'centro': ParagraphStyle('centro', fontName='Helvetica', fontSize=9, leading=12, alignment=TA_CENTER, textColor=INK),
    'pequeno': ParagraphStyle('pequeno', fontName='Helvetica', fontSize=8, leading=10.5, alignment=TA_CENTER, textColor=MUTED),
    'anexo': ParagraphStyle('anexo', fontName='Helvetica-Bold', fontSize=11, leading=15, textColor=INK, spaceAfter=8),
}


# ---------------------------------------------------------------- formatação
def moeda(valor):
    valor = Decimal(valor or 0)
    return f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def data_br(data):
    return data.strftime('%d/%m/%Y') if data else LACUNA


def data_extenso(data):
    return f'{data.day} de {MESES[data.month - 1]} de {data.year}'


def t(valor):
    """Escapa texto vindo do banco para uso seguro dentro de Paragraph."""
    return escape(str(valor)) if valor not in (None, '') else LACUNA


_UNIDADES = ['zero', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove', 'dez', 'onze', 'doze', 'treze', 'quatorze', 'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove']
_DEZENAS = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
_CENTENAS = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos']


def _ate_mil(n):
    if n == 100:
        return 'cem'
    partes = []
    if n >= 100:
        partes.append(_CENTENAS[n // 100]); n %= 100
    if n >= 20:
        partes.append(_DEZENAS[n // 10]); n %= 10
        if n:
            partes.append(_UNIDADES[n])
    elif n:
        partes.append(_UNIDADES[n])
    return ' e '.join(partes)


def _inteiro_extenso(n):
    if n == 0:
        return 'zero'
    nomes = (('', ''), ('mil', 'mil'), ('milhão', 'milhões'), ('bilhão', 'bilhões'))
    grupos = []
    indice = 0
    while n:
        grupos.append((n % 1000, indice)); n //= 1000; indice += 1
    partes = []
    for valor, indice in reversed(grupos):
        if not valor:
            continue
        singular, plural = nomes[indice]
        if indice == 0:
            texto = _ate_mil(valor)
        elif indice == 1:
            texto = 'mil' if valor == 1 else f'{_ate_mil(valor)} mil'
        else:
            texto = f'{_ate_mil(valor)} {singular if valor == 1 else plural}'
        partes.append((valor, texto))
    resultado = partes[0][1]
    for posicao, (valor, texto) in enumerate(partes[1:], start=1):
        ultimo = posicao == len(partes) - 1
        simples = valor < 100 or valor % 100 == 0
        resultado += (' e ' if simples else (' ' if ultimo else ', ')) + texto
    return resultado


def extenso_reais(valor):
    valor = Decimal(valor or 0).quantize(Decimal('0.01'))
    reais, centavos = int(valor), int((valor - int(valor)) * 100)
    partes = []
    if reais:
        sufixo = 'real' if reais == 1 else ('de reais' if reais % 1_000_000 == 0 else 'reais')
        partes.append(f'{_inteiro_extenso(reais)} {sufixo}')
    if centavos:
        partes.append(f'{_inteiro_extenso(centavos)} {"centavo" if centavos == 1 else "centavos"}')
    return ' e '.join(partes) or 'zero real'


def valor_completo(valor):
    return f'<b>{moeda(valor)}</b> ({extenso_reais(valor)})'


# ---------------------------------------------------------------- partes
def qualificacao_empresa(papel):
    nome = settings.COMPANY_LEGAL_NAME or settings.COMPANY_NAME
    doc = f'inscrita no CNPJ sob o nº {t(settings.COMPANY_CNPJ)}' if settings.COMPANY_CNPJ else f'inscrito(a) no CPF/CNPJ sob o nº {LACUNA}'
    endereco = f'com endereço em {t(settings.COMPANY_ADDRESS)}' if settings.COMPANY_ADDRESS else f'com endereço em {LACUNA}{LACUNA}'
    telefone = f', telefone {t(settings.COMPANY_PHONE)}' if settings.COMPANY_PHONE else ''
    return f'<b>{papel}:</b> <b>{t(nome)}</b>, {doc}, {endereco}{telefone}, doravante denominado(a) simplesmente <b>{papel}</b>.'


def qualificacao_cliente(cliente, papel, extra=''):
    cpf = t(cliente.cpf) if cliente.cpf else LACUNA
    endereco = t(cliente.endereco) if cliente.endereco else f'{LACUNA}{LACUNA}'
    return (f'<b>{papel}:</b> <b>{t(cliente.nome)}</b>, brasileiro(a), portador(a) do RG nº {LACUNA}, inscrito(a) no CPF sob o nº {cpf}, '
            f'residente e domiciliado(a) em {endereco}, telefone/WhatsApp {t(cliente.telefone)}{extra}, doravante denominado(a) simplesmente <b>{papel}</b>.')


# ---------------------------------------------------------------- blocos
class Instrumento:
    def __init__(self, titulo, subtitulo, rodape):
        self.titulo, self.subtitulo, self.rodape_texto = titulo, subtitulo, rodape
        self.story = [Paragraph(titulo, ESTILOS['titulo']), Paragraph(subtitulo, ESTILOS['subtitulo'])]
        self.numero = 0

    def partes(self, *paragrafos, preambulo):
        for paragrafo in paragrafos:
            self.story.append(Paragraph(paragrafo, ESTILOS['parte']))
        self.story.append(Paragraph(preambulo, ESTILOS['texto']))

    def clausula(self, titulo, *paragrafos, incisos=()):
        self.numero += 1
        ordinal = f'CLÁUSULA {self.numero}ª'
        bloco = [Paragraph(f'{ordinal} – {titulo.upper()}', ESTILOS['clausula']), Paragraph(paragrafos[0], ESTILOS['texto'])]
        romanos = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']
        for indice, inciso in enumerate(incisos):
            bloco.append(Paragraph(f'<b>{romanos[indice]}</b> – {inciso}', ESTILOS['inciso']))
        extras = paragrafos[1:]
        for indice, paragrafo in enumerate(extras, start=1):
            prefixo = '<b>Parágrafo único.</b> ' if len(extras) == 1 else f'<b>§ {indice}º</b> '
            bloco.append(Paragraph(prefixo + paragrafo, ESTILOS['texto']))
        self.story.append(KeepTogether(bloco[:2]))
        self.story.extend(bloco[2:])

    def assinaturas(self, data, papel_empresa, papel_cliente, nome_cliente):
        local = f'{LACUNA}, {data_extenso(data)}.'
        self.story.append(Spacer(1, 10))
        self.story.append(Paragraph('E, por estarem assim justas e contratadas, as partes assinam o presente instrumento em 2 (duas) vias de igual teor e forma, na presença das testemunhas abaixo.', ESTILOS['texto']))
        self.story.append(Spacer(1, 8))
        self.story.append(Paragraph(local, ESTILOS['centro']))
        linha = '_' * 42

        def assinatura(nome, papel):
            return [Paragraph(linha, ESTILOS['centro']), Paragraph(f'<b>{nome}</b>', ESTILOS['centro']), Paragraph(papel, ESTILOS['pequeno'])]

        def testemunha(numero):
            return [Paragraph(linha, ESTILOS['centro']), Paragraph(f'Testemunha {numero}', ESTILOS['centro']), Paragraph(f'Nome: {LACUNA}<br/>CPF: {LACUNA}', ESTILOS['pequeno'])]

        empresa = t(settings.COMPANY_LEGAL_NAME or settings.COMPANY_NAME)
        tabela = Table([[assinatura(empresa, papel_empresa), assinatura(t(nome_cliente), papel_cliente)], [Spacer(1, 18), Spacer(1, 18)], [testemunha(1), testemunha(2)]], colWidths=[8.3 * cm, 8.3 * cm])
        tabela.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, 0), 34), ('TOPPADDING', (0, 2), (-1, 2), 10)]))
        self.story.append(KeepTogether([tabela]))

    def anexo(self, titulo, cabecalho, linhas, larguras, observacao=None):
        self.story.append(PageBreak())
        self.story.append(Paragraph(titulo, ESTILOS['anexo']))
        if observacao:
            self.story.append(Paragraph(observacao, ESTILOS['texto']))
            self.story.append(Spacer(1, 6))
        tabela = Table([cabecalho, *linhas], colWidths=larguras, repeatRows=1)
        tabela.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), PRIMARY), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.8), ('GRID', (0, 0), (-1, -1), .4, LINE),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, SOFT]), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6), ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ]))
        self.story.append(tabela)

    def _rodape(self, canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(2 * cm, 1.55 * cm, A4[0] - 2 * cm, 1.55 * cm)
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 7.5)
        canvas.drawString(2 * cm, 1.05 * cm, self.rodape_texto)
        canvas.drawRightString(A4[0] - 2 * cm, 1.05 * cm, f'Rubricas: ________  ________     Página {doc.page}')
        canvas.restoreState()

    def resposta(self, nome_arquivo):
        buffer = BytesIO()
        documento = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=2.1 * cm, title=self.titulo.title(), author=settings.COMPANY_NAME)
        documento.build(self.story, onFirstPage=self._rodape, onLaterPages=self._rodape)
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename=nome_arquivo, content_type='application/pdf')


def hoje():
    return timezone.localdate()
