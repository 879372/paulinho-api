from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from core.models import Cliente
from .models import Aluguel, Moto, Movimento


class CaucaoFinanceiroTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user('caucao'))
        self.hoje = timezone.localdate()
        self.aluguel = Aluguel.objects.create(cliente=Cliente.objects.create(nome='Exemplo'), moto=Moto.objects.create(placa='ABC1D23', modelo='CG'), inicio=self.hoje, fim=self.hoje + timedelta(days=30), primeiro_vencimento=self.hoje, periodicidade='mensal', valor=300, valor_caucao=500)
        self.base = f'/api/operacoes/alugueis/{self.aluguel.pk}/caucao/'

    def lancar(self, acao, data=None):
        return self.client.post(self.base + acao + '/', {'data': str(data or self.hoje)}, format='json')

    def test_recebimento_devolucao_e_caixa_sem_duplicidade(self):
        self.assertEqual(Movimento.objects.count(), 0)
        resposta = self.lancar('receber')
        self.assertEqual(resposta.status_code, 201, resposta.data)
        self.assertEqual(resposta.data['caucao_financeiro']['recebimento']['valor'], 500)
        self.assertEqual(self.lancar('receber').status_code, 400)
        caixa = self.client.get('/api/operacoes/financeiro/').data
        motos = next(c for c in caixa['categorias'] if c['categoria'] == 'motos')
        self.assertEqual(motos['entradas'], 500)
        self.assertEqual(motos['saidas'], 0)
        self.assertIn(f'aluguel #{self.aluguel.pk}', caixa['lancamentos'][0]['descricao'])
        self.assertEqual(self.lancar('devolver').status_code, 201)
        self.assertEqual(self.lancar('devolver').status_code, 400)
        self.assertEqual(Movimento.objects.count(), 2)
        caixa = self.client.get('/api/operacoes/financeiro/').data
        motos = next(c for c in caixa['categorias'] if c['categoria'] == 'motos')
        self.assertEqual(motos['entradas'], 500)
        self.assertEqual(motos['saidas'], 500)
        self.assertEqual(motos['saldo'], 0)
        caixa = self.client.get('/api/operacoes/financeiro/').data
        self.assertEqual(caixa['saldo_periodo'], 0)
        self.assertEqual(caixa['saidas'], 500)
        self.assertFalse(self.aluguel.cobrancas.exists())

    def test_datas_e_operacoes_invalidas_nao_movimentam(self):
        self.assertEqual(self.lancar('devolver').status_code, 400)
        self.assertEqual(self.lancar('receber', self.hoje + timedelta(days=1)).status_code, 400)
        self.assertEqual(Movimento.objects.count(), 0)
        self.assertEqual(self.lancar('receber').status_code, 201)
        self.assertEqual(self.lancar('devolver', self.hoje - timedelta(days=1)).status_code, 400)
        self.assertEqual(self.lancar('devolver', self.hoje + timedelta(days=1)).status_code, 400)
        self.assertEqual(Movimento.objects.count(), 1)
        self.assertEqual(self.client.patch(self.base, {'valor_caucao': 600}, format='json').status_code, 400)

    def test_sem_valor_sem_caucao_e_sem_login(self):
        self.assertEqual(self.lancar('devolver').status_code, 400)
        for valor in (None, 0):
            self.aluguel.valor_caucao = valor
            self.aluguel.save()
            self.assertEqual(self.lancar('receber').status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.lancar('receber').status_code, 401)
        self.assertEqual(Movimento.objects.count(), 0)

    def test_recebimento_permitido_apos_assinatura_sem_mudar_contrato(self):
        self.aluguel.assinatura_status = 'assinado'
        self.aluguel.save()
        self.assertEqual(self.lancar('receber').status_code, 201)
        self.assertEqual(self.lancar('devolver').status_code, 201)
        self.aluguel.refresh_from_db()
        self.assertEqual(self.aluguel.valor_caucao, 500)
        self.assertEqual(self.aluguel.assinatura_status, 'assinado')
