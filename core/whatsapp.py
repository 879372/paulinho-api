import re

import requests
from django.conf import settings


def normalizar_numero_whatsapp(numero):
    numero = re.sub(r'\D', '', str(numero or ''))
    # Cadastros brasileiros normalmente armazenam apenas DDD + número.
    # A Evolution API requer o número completo com o código do país.
    if len(numero) in (10, 11):
        return f'55{numero}'
    return numero


def enviar_whatsapp(numero, texto):
    if not all([settings.EVOLUTION_API_URL, settings.EVOLUTION_API_KEY, settings.EVOLUTION_INSTANCE]):
        raise RuntimeError('Evolution API não configurada.')

    url = f'{settings.EVOLUTION_API_URL.rstrip('/')}/message/sendText/{settings.EVOLUTION_INSTANCE}'

    response = requests.post(
        url,
        headers={'apikey': settings.EVOLUTION_API_KEY},
        json={
            'number': normalizar_numero_whatsapp(numero),
            'text': texto,
        },
        timeout=20,
    )
    if not response.ok:
        detalhe = response.text.strip()[:1000]
        raise RuntimeError(f'Evolution API respondeu HTTP {response.status_code}: {detalhe}')
    return response.json()
