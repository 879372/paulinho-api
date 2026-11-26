"""Base compartilhada dos instrumentos contratuais em PDF (mútuo e locação de moto).

Estrutura inspirada nos modelos usuais de mercado: qualificação das partes,
cláusulas numeradas, assinatura das partes (eletrônica, CPC art. 784, § 4º) e anexos.
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
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PRIMARY = colors.HexColor('#0B6B53')
INK = colors.HexColor('#0F1A16')
MUTED = colors.HexColor('#55645E')
LINE = colors.HexColor('#D5DDDA')
SOFT = colors.HexColor('#EEF5F2')
LACUNA = '_' * 22

MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']

def estilos(escala=1.0):
    def e(nome, tamanho, entrelinha, **extra):
        return ParagraphStyle(nome, fontSize=tamanho * escala, leading=entrelinha * escala, textColor=extra.pop('textColor', INK), fontName=extra.pop('fontName', 'Helvetica'), **extra)
    return {
        'titulo': e('titulo', 12.5, 15, fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=1),
        'subtitulo': e('subtitulo', 8, 10, alignment=TA_CENTER, textColor=MUTED, spaceAfter=8 * escala),
        'parte': e('parte', 8.6, 11.4, alignment=TA_JUSTIFY, spaceAfter=4 * escala),
        'clausula': e('clausula', 8.6, 11, fontName='Helvetica-Bold', textColor=PRIMARY, spaceBefore=5 * escala, spaceAfter=1.5),
        'texto': e('texto', 8.6, 11.4, alignment=TA_JUSTIFY, spaceAfter=2 * escala),
        'inciso': e('inciso', 8.6, 11.4, alignment=TA_JUSTIFY, leftIndent=12, spaceAfter=1.5),
        'centro': e('centro', 8.4, 10.5, alignment=TA_CENTER),
        'pequeno': e('pequeno', 7.4, 9.2, alignment=TA_CENTER, textColor=MUTED),
        'anexo': e('anexo', 8.6, 11, fontName='Helvetica-Bold', textColor=PRIMARY, spaceBefore=8 * escala, spaceAfter=3),
        'celula': e('celula', 7.6, 9.4),
    }


ESTILOS = estilos()


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
    if not settings.COMPANY_CNPJ and settings.COMPANY_CPF:
        doc = f'inscrito(a) no CPF sob o nº {t(settings.COMPANY_CPF)}'
    endereco = f'com endereço em {t(settings.COMPANY_ADDRESS)}' if settings.COMPANY_ADDRESS else f'com endereço em {LACUNA}{LACUNA}'
    telefone = f', telefone {t(settings.COMPANY_PHONE)}' if settings.COMPANY_PHONE else ''
    return f'<b>{papel}:</b> <b>{t(nome)}</b>, {doc}, {endereco}{telefone}, doravante denominado(a) simplesmente <b>{papel}</b>.'


def qualificacao_cliente(cliente, papel, extra=''):
    cpf = t(cliente.cpf) if cliente.cpf else LACUNA
    endereco = t(cliente.endereco) if cliente.endereco else f'{LACUNA}{LACUNA}'
    return (f'<b>{papel}:</b> <b>{t(cliente.nome)}</b>, brasileiro(a), portador(a) do RG nº {LACUNA}, inscrito(a) no CPF sob o nº {cpf}, '
            f'residente e domiciliado(a) em {endereco}, telefone/WhatsApp {t(cliente.telefone)}{extra}, doravante denominado(a) simplesmente <b>{papel}</b>.')


# ---------------------------------------------------------------- blocos
NIVEIS = (1.0, .95, .9, .85, .8)


class Instrumento:
    """Monta um instrumento contratual. `nivel` controla a compactação (0 = normal)."""

    def __init__(self, titulo, subtitulo, rodape, nivel=0):
        self.titulo, self.rodape_texto, self.nivel = titulo, rodape, nivel
        self.escala = NIVEIS[min(nivel, len(NIVEIS) - 1)]
        self.e = estilos(self.escala)
        self.resumir = nivel >= 2
        self.story = [Paragraph(titulo, self.e['titulo']), Paragraph(subtitulo, self.e['subtitulo'])]
        self.numero = 0
        self.paginas = 0

    def p(self, texto, estilo='texto'):
        self.story.append(Paragraph(texto, self.e[estilo]))

    def partes(self, *paragrafos, preambulo):
        for paragrafo in paragrafos:
            self.p(paragrafo, 'parte')
        self.p(preambulo)

    def clausula(self, titulo, *paragrafos, incisos=()):
        self.numero += 1
        bloco = [Paragraph(f'CLÁUSULA {self.numero}ª – {titulo.upper()}', self.e['clausula']), Paragraph(paragrafos[0], self.e['texto'])]
        romanos = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']
        for indice, inciso in enumerate(incisos):
            bloco.append(Paragraph(f'<b>{romanos[indice]}</b> – {inciso}', self.e['inciso']))
        extras = paragrafos[1:]
        for indice, paragrafo in enumerate(extras, start=1):
            prefixo = '<b>Parágrafo único.</b> ' if len(extras) == 1 else f'<b>§ {indice}º</b> '
            bloco.append(Paragraph(prefixo + paragrafo, self.e['texto']))
        self.story.append(KeepTogether(bloco[:2]))
        self.story.extend(bloco[2:])

    def assinaturas(self, data, papel_empresa, papel_cliente, nome_cliente):
        self.story.append(Spacer(1, 4 * self.escala))
        self.p('E, por estarem assim justas e contratadas, as partes assinam o presente instrumento, admitida a assinatura eletrônica nos termos da Lei nº 14.063/2020, reconhecendo-a como válida e eficaz para todos os fins.')
        linha = '_' * 40

        def assinatura(nome, papel):
            return [Paragraph(linha, self.e['centro']), Paragraph(f'<b>{nome}</b>', self.e['centro']), Paragraph(papel, self.e['pequeno'])]

        empresa = t(settings.COMPANY_LEGAL_NAME or settings.COMPANY_NAME)
        tabela = Table([[Paragraph(f'{LACUNA}, {data_extenso(data)}.', self.e['centro']), ''], [assinatura(empresa, papel_empresa), assinatura(t(nome_cliente), papel_cliente)]], colWidths=[8.6 * cm, 8.6 * cm])
        tabela.setStyle(TableStyle([('SPAN', (0, 0), (-1, 0)), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 1), (-1, 1), 26 * self.escala), ('TOPPADDING', (0, 0), (-1, 0), 4)]))
        self.story.append(KeepTogether([tabela]))

    def _tabela(self, linhas, larguras, cabecalho_linhas=1):
        tabela = Table(linhas, colWidths=larguras, repeatRows=cabecalho_linhas)
        tabela.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, cabecalho_linhas - 1), PRIMARY), ('TEXTCOLOR', (0, 0), (-1, cabecalho_linhas - 1), colors.white),
            ('FONTNAME', (0, 0), (-1, cabecalho_linhas - 1), 'Helvetica-Bold'), ('FONTNAME', (0, cabecalho_linhas), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.6 * self.escala), ('LEADING', (0, 0), (-1, -1), 9 * self.escala),
            ('GRID', (0, 0), (-1, -1), .35, LINE), ('ROWBACKGROUNDS', (0, cabecalho_linhas), (-1, -1), [colors.white, SOFT]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 2.2 * self.escala), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.2 * self.escala),
            ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        return tabela

    def cronograma(self, titulo, itens, resumo, grupos=3):
        """itens: lista de (vencimento, valor). Em grade de `grupos` colunas; resumido quando não cabe."""
        self.story.append(Paragraph(titulo, self.e['anexo']))
        limite = {0: 60, 1: 45, 2: 24, 3: 12}.get(self.nivel, 0)
        if not itens or len(itens) > limite:
            self.p(resumo + (' O cronograma completo fica disponível no sistema e no comprovante de parcelas.' if itens else ''))
            return
        self.p(resumo)
        linhas_por_grupo = -(-len(itens) // grupos)
        cabecalho = ['Nº', 'Vencimento', 'Valor'] * grupos
        linhas = []
        for linha in range(linhas_por_grupo):
            celulas = []
            for grupo in range(grupos):
                indice = grupo * linhas_por_grupo + linha
                celulas += [str(indice + 1), data_br(itens[indice][0]), moeda(itens[indice][1])] if indice < len(itens) else ['', '', '']
            linhas.append(celulas)
        largura = 17.2 * cm / grupos
        self.story.append(self._tabela([cabecalho, *linhas], [largura * .16, largura * .42, largura * .42] * grupos))

    def checklist(self, titulo, itens, observacao, grupos=2):
        self.story.append(Paragraph(titulo, self.e['anexo']))
        self.p(observacao)
        por_grupo = -(-len(itens) // grupos)
        linhas = []
        for linha in range(por_grupo):
            celulas = []
            for grupo in range(grupos):
                indice = grupo * por_grupo + linha
                celulas += [itens[indice], '', ''] if indice < len(itens) else ['', '', '']
            linhas.append(celulas)
        largura = 17.2 * cm / grupos
        self.story.append(self._tabela([['Item', 'Entrega', 'Devolução'] * grupos, *linhas], [largura * .58, largura * .21, largura * .21] * grupos))

    def _rodape(self, canvas, doc):
        self.paginas = max(self.paginas, doc.page)
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(1.9 * cm, 1.25 * cm, A4[0] - 1.9 * cm, 1.25 * cm)
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 7)
        canvas.drawString(1.9 * cm, .85 * cm, self.rodape_texto)
        canvas.drawRightString(A4[0] - 1.9 * cm, .85 * cm, f'Página {doc.page}')
        canvas.restoreState()

    def construir(self):
        buffer = BytesIO()
        documento = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.9 * cm, rightMargin=1.9 * cm, topMargin=1.4 * cm, bottomMargin=1.6 * cm, title=self.titulo.title(), author=settings.COMPANY_NAME)
        documento.build(self.story, onFirstPage=self._rodape, onLaterPages=self._rodape)
        return buffer.getvalue(), self.paginas


def gerar_pdf(montar, max_paginas=2):
    """Monta o instrumento em níveis crescentes de compactação até caber em `max_paginas`."""
    for nivel in range(len(NIVEIS)):
        conteudo, paginas = montar(nivel).construir()
        if paginas <= max_paginas:
            return conteudo
    return conteudo


def resposta_pdf(conteudo, nome_arquivo):
    return FileResponse(BytesIO(conteudo), as_attachment=True, filename=nome_arquivo, content_type='application/pdf')


def hoje():
    return timezone.localdate()
