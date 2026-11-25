from decimal import Decimal
from hashlib import sha256
import time
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.utils import timezone
from core.api.cobrancas.services import gerar_juros_mensais, atualizar_atrasos
from core.models import Contrato, LembreteDiario, Parcela
from core.whatsapp import enviar_whatsapp
from core.management.commands.enviar_cobrancas_do_dia import contas_vencendo_em, montar_resumo, moeda
from core.management.commands.enviar_lembretes_atraso import referencia_parcela
from operacoes.models import CobrancaAluguel


def verificar_conexao():
    if not all([settings.EVOLUTION_API_URL, settings.EVOLUTION_API_KEY, settings.EVOLUTION_INSTANCE, settings.OWNER_WHATSAPP]):
        raise CommandError('Configure Evolution e OWNER_WHATSAPP antes de ativar os lembretes.')
    try:
        resposta = requests.get(f"{settings.EVOLUTION_API_URL.rstrip('/')}/instance/connectionState/{quote(settings.EVOLUTION_INSTANCE, safe='')}", headers={'apikey': settings.EVOLUTION_API_KEY}, timeout=20)
        resposta.raise_for_status()
        conectado = resposta.json().get('instance', {}).get('state') == 'open'
    except (requests.RequestException, ValueError):
        raise CommandError('Não foi possível verificar a conexão da Evolution.')
    if not conectado:
        raise CommandError('A instância WhatsApp está desconectada.')


def tarefas(hoje):
    parcelas = list(Parcela.objects.select_related('contrato__cliente').filter(status__in=[Parcela.Status.PENDENTE, Parcela.Status.ATRASADA], data_vencimento__lte=hoje).exclude(contrato__status__in=[Contrato.Status.CANCELADO, Contrato.Status.QUITADO, Contrato.Status.RENEGOCIADO]).order_by('data_vencimento', 'id'))
    alugueis = list(CobrancaAluguel.objects.select_related('aluguel__cliente', 'aluguel__moto').filter(pago_em__isnull=True, vencimento__lte=hoje).order_by('vencimento', 'id'))
    resumo = montar_resumo(parcelas, contas_vencendo_em(hoje))
    if alugueis:
        linhas = ['','', '*ALUGUÉIS DE MOTOS*']
        for item in alugueis:
            situacao = 'Em atraso' if item.vencimento < hoje else 'Vence hoje'
            linhas.append(f'• {item.aluguel.cliente.nome} · {item.aluguel.moto.placa} · {moeda(item.valor)} · {situacao} ({item.vencimento:%d/%m/%Y})')
        total = sum((item.valor for item in alugueis), Decimal('0')) + sum((p.valor for p in parcelas), Decimal('0'))
        linhas.extend(['', f'*TOTAL GERAL A RECEBER: {moeda(total)}*'])
        resumo += '\n'.join(linhas)
    versao = sha256(f'{settings.OWNER_WHATSAPP}\n{resumo}'.encode()).hexdigest()[:24]
    yield f'resumo-proprietario-{versao}', settings.OWNER_WHATSAPP, resumo
    for parcela in parcelas:
        _, descricao, prazo = referencia_parcela(parcela)
        situacao = 'vence hoje' if parcela.data_vencimento == hoje else 'está em atraso'
        texto = f'Olá, {parcela.contrato.cliente.nome}!\nLembrete de pagamento: {descricao} · {prazo}.\nValor: {moeda(parcela.valor)}\nVencimento: {parcela.data_vencimento:%d/%m/%Y}\nEste pagamento {situacao}. Se já pagou, entre em contato para conferirmos. Obrigado!'
        yield f'parcela-{parcela.pk}', parcela.contrato.cliente.telefone, texto
    for item in alugueis:
        situacao = 'vence hoje' if item.vencimento == hoje else 'está em atraso'
        texto = f'Olá, {item.aluguel.cliente.nome}!\nO aluguel da moto {item.aluguel.moto.placa} {situacao}.\nValor: {moeda(item.valor)}\nVencimento: {item.vencimento:%d/%m/%Y}\nSe já pagou, entre em contato para conferirmos. Obrigado!'
        yield f'aluguel-{item.pk}', item.aluguel.cliente.telefone, texto


class Command(BaseCommand):
    help = 'Resumo do responsável e lembretes de parcelas/aluguéis, uma vez ao dia.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Valida conexão e conta tarefas sem enviar mensagens ou alterar dados.')

        parser.add_argument('--somente-resumo', action='store_true', help='Atualiza somente o resumo do proprietário, sem cobrar clientes.')

    def handle(self, *args, **options):
        verificar_conexao()
        hoje = timezone.localdate()
        if not options['dry_run']:
            gerar_juros_mensais(hoje)
            atualizar_atrasos()
        enviados = falhas = ignorados = previstos = 0
        for chave, telefone, texto in tarefas(hoje):
            if options['somente_resumo'] and not chave.startswith('resumo-proprietario-'):
                continue
            previstos += 1
            if options['dry_run']:
                continue
            registro, criado = LembreteDiario.objects.get_or_create(chave=chave, data=hoje)
            if not criado:
                ignorados += 1
                continue
            try:
                enviar_whatsapp(telefone, texto)
            except Exception:
                registro.status = 'falha'
                falhas += 1
                self.stderr.write(f'Falha no lembrete {chave}; verificar antes de reenviar.')
            else:
                registro.status = 'enviado'
                enviados += 1
            registro.save(update_fields=['status', 'atualizado_em'])
            time.sleep(getattr(settings, 'LEMBRETES_INTERVALO', 1))
        self.stdout.write(f'Conexão OK. Previstos: {previstos}; enviados: {enviados}; já processados: {ignorados}; falhas: {falhas}.')
        if falhas:
            raise CommandError('Houve falhas de envio; consulte o registro de lembretes.')
