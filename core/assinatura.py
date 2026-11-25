"""Assinatura eletrônica via Autentique (API GraphQL v2).

Fluxo: o app gera o PDF (máx. 2 páginas), envia à Autentique com o cliente como signatário
por WhatsApp e a empresa por e-mail (ou link). O status é atualizado sob demanda, consultando
a API — não depende de webhook, então funciona também em servidor sem endereço público.
"""
import json
import re

import requests
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status as http
from rest_framework.response import Response

API_URL = 'https://api.autentique.com.br/v2/graphql'

CRIAR = '''mutation CriarDocumento($document: DocumentInput!, $signers: [SignerInput!]!, $file: Upload!) {
  createDocument(sandbox: %s, document: $document, signers: $signers, file: $file) {
    id
    signatures { public_id name email action { name } link { short_link } }
  }
}'''

CONSULTAR = '''query Documento {
  document(id: %s) {
    id
    files { signed }
    signatures { public_id name email action { name } link { short_link } signed { created_at } rejected { created_at } }
  }
}'''


class AssinaturaErro(Exception):
    pass


def configurado():
    return bool(settings.AUTENTIQUE_TOKEN)


def _cabecalho():
    return {'Authorization': f'Bearer {settings.AUTENTIQUE_TOKEN}'}


def _resposta(response):
    if response.status_code == 401:
        raise AssinaturaErro('Token da Autentique inválido. Confira AUTENTIQUE_TOKEN.')
    try:
        corpo = response.json()
    except ValueError:
        raise AssinaturaErro(f'A Autentique respondeu HTTP {response.status_code}.')
    if corpo.get('errors'):
        mensagem = '; '.join(str(erro.get('message', erro)) for erro in corpo['errors'])
        raise AssinaturaErro(f'Autentique: {mensagem}')
    return corpo.get('data') or {}


def telefone_e164(telefone):
    digitos = re.sub(r'\D', '', telefone or '')
    if len(digitos) in (10, 11):
        digitos = f'55{digitos}'
    if not re.fullmatch(r'55\d{10,11}', digitos):
        raise AssinaturaErro('O telefone do cliente precisa ter DDD + número para receber o link pelo WhatsApp.')
    return f'+{digitos}'


def enviar_documento(conteudo_pdf, nome_documento, nome_arquivo, cliente):
    empresa = {'email': settings.AUTENTIQUE_EMAIL_EMPRESA, 'action': 'SIGN'} if settings.AUTENTIQUE_EMAIL_EMPRESA else {'name': settings.COMPANY_NAME, 'action': 'SIGN'}
    signatarios = [
        {'name': cliente.nome, 'phone': telefone_e164(cliente.telefone), 'delivery_method': 'DELIVERY_METHOD_WHATSAPP', 'action': 'SIGN'},
        empresa,
    ]
    operacoes = {
        'query': CRIAR % ('true' if settings.AUTENTIQUE_SANDBOX else 'false'),
        'variables': {'document': {'name': nome_documento, 'refusable': True}, 'signers': signatarios, 'file': None},
    }
    try:
        response = requests.post(API_URL, headers=_cabecalho(), timeout=40,
                                 data={'operations': json.dumps(operacoes), 'map': json.dumps({'file': ['variables.file']})},
                                 files={'file': (nome_arquivo, conteudo_pdf, 'application/pdf')})
    except requests.RequestException as erro:
        raise AssinaturaErro(f'Não foi possível conectar à Autentique: {erro}')
    documento = _resposta(response).get('createDocument') or {}
    if not documento.get('id'):
        raise AssinaturaErro('A Autentique não retornou o documento criado.')
    return documento


def consultar_documento(documento_id):
    try:
        response = requests.post(API_URL, headers=_cabecalho(), json={'query': CONSULTAR % json.dumps(str(documento_id))}, timeout=20)
    except requests.RequestException as erro:
        raise AssinaturaErro(f'Não foi possível conectar à Autentique: {erro}')
    documento = _resposta(response).get('document')
    if not documento:
        raise AssinaturaErro('Documento não encontrado na Autentique (documentos de teste são apagados após alguns dias).')
    return documento


def _link_empresa(documento):
    for assinatura in documento.get('signatures') or []:
        if (assinatura.get('action') or {}).get('name') == 'SIGN' and assinatura.get('name') == settings.COMPANY_NAME and not assinatura.get('email'):
            return ((assinatura.get('link') or {}).get('short_link')) or ''
    return ''


def _status(documento):
    signatarios = [a for a in documento.get('signatures') or [] if (a.get('action') or {}).get('name') == 'SIGN']
    if any(a.get('rejected') for a in signatarios):
        return 'recusado'
    if signatarios and all(a.get('signed') for a in signatarios):
        return 'assinado'
    return 'pendente'


def resumo(objeto, documento=None):
    dados = {
        'assinatura_status': objeto.assinatura_status, 'assinatura_enviada_em': objeto.assinatura_enviada_em,
        'assinatura_concluida_em': objeto.assinatura_concluida_em, 'assinatura_link_empresa': objeto.assinatura_link_empresa,
        'assinatura_sandbox': objeto.assinatura_sandbox, 'configurado': configurado(),
    }
    if documento:
        dados['signatarios'] = [{'nome': a.get('name') or a.get('email'), 'assinou': bool(a.get('signed')), 'recusou': bool(a.get('rejected'))}
                                for a in documento.get('signatures') or [] if (a.get('action') or {}).get('name') == 'SIGN']
    return dados


# ------------------------------------------------------------------ views compartilhadas
def view_assinatura(request, objeto, gerar_pdf, nome_documento, nome_arquivo, cliente):
    """GET atualiza o status a partir da Autentique; POST envia o contrato para assinatura."""
    if not configurado():
        return Response({'detail': 'Assinatura eletrônica não configurada. Defina AUTENTIQUE_TOKEN no .env do backend.', **resumo(objeto)},
                        status=http.HTTP_400_BAD_REQUEST if request.method == 'POST' else http.HTTP_200_OK)
    try:
        if request.method == 'POST':
            if objeto.assinatura_status in ('pendente', 'assinado') and not request.data.get('reenviar'):
                return Response({'detail': 'Este contrato já foi enviado para assinatura.'}, status=http.HTTP_400_BAD_REQUEST)
            documento = enviar_documento(gerar_pdf(), nome_documento, nome_arquivo, cliente)
            objeto.assinatura_id = documento['id']
            objeto.assinatura_status = 'pendente'
            objeto.assinatura_enviada_em = timezone.now()
            objeto.assinatura_concluida_em = None
            objeto.assinatura_sandbox = settings.AUTENTIQUE_SANDBOX
            objeto.assinatura_link_empresa = _link_empresa(documento)
            objeto.save(update_fields=['assinatura_id', 'assinatura_status', 'assinatura_enviada_em', 'assinatura_concluida_em', 'assinatura_sandbox', 'assinatura_link_empresa'])
            return Response(resumo(objeto, documento), status=http.HTTP_201_CREATED)
        if not objeto.assinatura_id:
            return Response(resumo(objeto))
        documento = consultar_documento(objeto.assinatura_id)
        novo = _status(documento)
        if novo != objeto.assinatura_status:
            objeto.assinatura_status = novo
            objeto.assinatura_concluida_em = timezone.now() if novo == 'assinado' else None
            objeto.save(update_fields=['assinatura_status', 'assinatura_concluida_em'])
        return Response(resumo(objeto, documento))
    except AssinaturaErro as erro:
        return Response({'detail': str(erro)}, status=http.HTTP_502_BAD_GATEWAY)


def view_pdf_assinado(objeto, nome_arquivo):
    if objeto.assinatura_status != 'assinado' or not objeto.assinatura_id:
        return Response({'detail': 'O contrato ainda não foi assinado por todas as partes.'}, status=http.HTTP_400_BAD_REQUEST)
    try:
        url = (consultar_documento(objeto.assinatura_id).get('files') or {}).get('signed')
        if not url:
            raise AssinaturaErro('A Autentique ainda não disponibilizou o PDF assinado.')
        arquivo = requests.get(url, headers=_cabecalho(), timeout=40)
        if not arquivo.ok:
            raise AssinaturaErro(f'Falha ao baixar o PDF assinado (HTTP {arquivo.status_code}).')
    except (AssinaturaErro, requests.RequestException) as erro:
        return Response({'detail': str(erro)}, status=http.HTTP_502_BAD_GATEWAY)
    resposta = HttpResponse(arquivo.content, content_type='application/pdf')
    resposta['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'
    return resposta
