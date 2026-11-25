from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from core.models import Cliente, Contrato, Parcela
from core.api.clientes.pdf import valor_quitacao
from core.management.commands.enviar_lembretes_diarios import tarefas
from operacoes.models import Moto, Aluguel, CobrancaAluguel, Movimento


class AdiamentoTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user('adiamento'))
        self.hoje = timezone.localdate()
        self.cliente = Cliente.objects.create(nome='Cliente', telefone='84999990000')
        self.contrato = Contrato.objects.create(cliente=self.cliente, tipo='emprestimo_tradicional', data_inicio=self.hoje, valor_principal=Decimal('400'), valor_parcela=Decimal('200'), qtd_parcelas=2, periodicidade='mensal')
        self.atual = Parcela.objects.create(contrato=self.contrato, numero=1, valor=Decimal('200'), data_vencimento=self.hoje)
        self.proxima = Parcela.objects.create(contrato=self.contrato, numero=2, valor=Decimal('200'), data_vencimento=self.hoje+timedelta(days=30))

    def adiar(self, url):
        previa = self.client.get(url)
        self.assertEqual(previa.status_code, 200, previa.data)
        resposta = self.client.post(url, {'versao': previa.data['versao']}, format='json')
        self.assertEqual(resposta.status_code, 200, resposta.data)
        return resposta

    def test_soma_preserva_historico_saldo_e_nao_registra_recebimento(self):
        url=f'/api/parcelas/{self.atual.pk}/adiar/'
        self.adiar(url)
        self.atual.refresh_from_db(); self.proxima.refresh_from_db()
        self.assertEqual(self.atual.status, 'transferida')
        self.assertEqual(self.atual.valor, Decimal('200'))
        self.assertEqual(self.atual.transferida_para_id, self.proxima.pk)
        self.assertEqual(self.proxima.valor, Decimal('400'))
        self.assertEqual(valor_quitacao(self.contrato), Decimal('400'))
        self.assertEqual(Movimento.objects.count(), 0)
        self.assertEqual(self.client.post(url,{}).status_code, 400)
        self.assertEqual(self.client.patch(f'/api/parcelas/{self.atual.pk}/dar-baixa/',{'valor_pago':'200','forma_pagamento':'pix'}).status_code, 400)
        chaves = [chave for chave, _, _ in tarefas(self.hoje)]
        self.assertNotIn(f'parcela-{self.atual.pk}', chaves)
        self.assertEqual(self.client.get('/api/dashboard/').data['vencendo_hoje'], 0)

    def test_previa_nao_muda_dados_e_detecta_destino_alterado(self):
        url=f'/api/parcelas/{self.atual.pk}/adiar/'
        previa=self.client.get(url)
        self.atual.refresh_from_db()
        self.assertEqual(self.atual.status,'pendente')
        self.proxima.valor=Decimal('250'); self.proxima.save()
        self.assertEqual(self.client.post(url,{'versao':previa.data['versao']}).status_code,409)
        self.atual.refresh_from_db()
        self.assertIsNone(self.atual.transferida_para_id)

    def test_ultima_parcela_prorroga_so_o_saldo(self):
        self.adiar(f'/api/parcelas/{self.proxima.pk}/adiar/')
        self.proxima.refresh_from_db()
        self.assertEqual(self.proxima.transferida_para.valor,Decimal('200'))
        self.assertEqual(self.contrato.parcelas.count(),3)
        self.assertEqual(valor_quitacao(self.contrato),Decimal('400'))

    def test_somente_juros_soma_base_do_proximo_periodo_sem_capitalizar(self):
        self.contrato.tipo='emprestimo_somente_juros'; self.contrato.valor_juros_mensal=Decimal('200'); self.contrato.save()
        self.proxima.delete()
        self.atual.tipo='juros_mensal'; self.atual.numero=None; self.atual.save()
        self.adiar(f'/api/parcelas/{self.atual.pk}/adiar/')
        self.atual.refresh_from_db()
        seguinte=self.atual.transferida_para
        self.assertEqual(seguinte.valor,Decimal('400'))
        self.adiar(f'/api/parcelas/{seguinte.pk}/adiar/')
        seguinte.refresh_from_db()
        self.assertEqual(seguinte.transferida_para.valor,Decimal('600'))
        self.assertEqual(Movimento.objects.count(),0)

    def test_aluguel_transfere_e_recebe_somente_o_total_final(self):
        moto=Moto.objects.create(placa='ABC1D23',modelo='CG')
        aluguel=Aluguel.objects.create(moto=moto,cliente=self.cliente,inicio=self.hoje,fim=self.hoje+timedelta(days=14),primeiro_vencimento=self.hoje,valor=100,periodicidade='semanal')
        atual=CobrancaAluguel.objects.create(aluguel=aluguel,valor=100,vencimento=self.hoje)
        proxima=CobrancaAluguel.objects.create(aluguel=aluguel,valor=100,vencimento=self.hoje+timedelta(days=7))
        self.adiar(f'/api/operacoes/alugueis/cobrancas/{atual.pk}/adiar/')
        atual.refresh_from_db(); proxima.refresh_from_db()
        self.assertEqual(atual.transferida_para_id,proxima.pk)
        self.assertEqual(proxima.valor,Decimal('200'))
        self.assertEqual(self.client.post(f'/api/operacoes/alugueis/cobrancas/{atual.pk}/receber/',{'data':str(self.hoje)}).status_code,400)
        pendentes=self.client.get('/api/operacoes/alugueis/cobrancas/',{'status':'pendente,atrasada'}).data['results']
        self.assertEqual([item['id'] for item in pendentes],[proxima.pk])
        chaves=[chave for chave,_,_ in tarefas(self.hoje)]
        self.assertNotIn(f'aluguel-{atual.pk}',chaves)
        self.assertEqual(self.client.post(f'/api/operacoes/alugueis/cobrancas/{proxima.pk}/receber/',{'data':str(self.hoje)}).status_code,200)
        self.assertEqual(Movimento.objects.get().valor,Decimal('200'))

    def test_rejeita_pago_e_exige_login(self):
        self.atual.status='paga'; self.atual.save()
        url=f'/api/parcelas/{self.atual.pk}/adiar/'
        self.assertEqual(self.client.get(url).status_code,400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code,401)
