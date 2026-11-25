from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from core.models import Cliente, Contrato, Parcela
from .models import Moto, Movimento, CobrancaAluguel


class OperacoesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user('gestor'))
        self.cliente = Cliente.objects.create(nome='Cliente de teste', telefone='85988887777')
        self.moto = Moto.objects.create(placa='ABC1D23', modelo='CG 160')
        self.hoje = date.today()

    def post(self, path, data):
        return self.client.post('/api/operacoes/' + path, data, format='json')

    def aluguel(self, **changes):
        payload = dict(moto=self.moto.pk, cliente=self.cliente.pk, inicio=str(self.hoje), fim=str(self.hoje + timedelta(days=14)), valor='100.00', periodicidade='semanal', primeiro_vencimento=str(self.hoje))
        payload.update(changes)
        return self.post('alugueis/', payload)

    def test_todas_rotas_exigem_autenticacao(self):
        self.client.force_authenticate(None)
        for path in ['motos/', 'alugueis/', 'animais/', 'movimentos/', 'financeiro/']:
            self.assertEqual(self.client.get('/api/operacoes/' + path).status_code, 401)

    def test_aluguel_reserva_periodo_e_nao_permite_sobreposicao(self):
        response = self.aluguel()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data['cobrancas']), 3)
        self.assertEqual(self.aluguel().status_code, 400)
        self.assertEqual(CobrancaAluguel.objects.count(), 3)
        self.assertEqual(self.aluguel(inicio=str(self.hoje + timedelta(days=15)), fim=str(self.hoje + timedelta(days=29)), primeiro_vencimento=str(self.hoje + timedelta(days=15))).status_code, 201)

    def test_moto_em_manutencao_e_periodos_invalidos(self):
        self.assertEqual(self.aluguel(fim=str(self.hoje - timedelta(days=1))).status_code, 400)
        self.moto.em_manutencao = True
        self.moto.save()
        self.assertEqual(self.aluguel().status_code, 400)

    def test_recebimento_registra_caixa_uma_vez(self):
        cobranca = self.aluguel().data['cobrancas'][0]['id']
        path = f'alugueis/cobrancas/{cobranca}/receber/'
        self.assertEqual(self.post(path, {'data': str(self.hoje)}).status_code, 200)
        self.assertEqual(self.post(path, {'data': str(self.hoje)}).status_code, 400)
        self.assertEqual(Movimento.objects.count(), 1)
        resumo = self.client.get('/api/operacoes/financeiro/').data
        self.assertEqual(resumo['entradas'], Decimal('100'))

    def test_compra_alimentacao_e_venda_apuram_resultado_do_lote(self):
        response = self.post('animais/', {'identificacao': 'Ovinos A', 'especie': 'Ovinos', 'quantidade': 10, 'data_aquisicao': str(self.hoje), 'valor_compra': '1000.00'})
        self.assertEqual(response.status_code, 201, response.data)
        lote = response.data['id']
        for tipo, categoria, valor in [('saida', 'alimentacao', '200.00'), ('entrada', 'venda_animais', '1500.00')]:
            response = self.post('movimentos/', {'lote': lote, 'descricao': categoria, 'categoria': categoria, 'tipo': tipo, 'valor': valor, 'data': str(self.hoje)})
            self.assertEqual(response.status_code, 201, response.data)
        resultado = self.client.get('/api/operacoes/financeiro/').data
        self.assertEqual(resultado['lotes'][0]['despesas'], Decimal('1200'))
        self.assertEqual(resultado['lotes'][0]['resultado'], Decimal('300'))
        self.assertEqual(resultado['saldo_periodo'], Decimal('300'))

    def test_rejeita_categoria_incoerente_valor_negativo_e_pagamento_futuro(self):
        payload = {'descricao': 'Ração', 'categoria': 'alimentacao', 'tipo': 'saida', 'valor': '100', 'data': str(self.hoje)}
        self.assertEqual(self.post('movimentos/', payload).status_code, 400)
        payload.update(categoria='outros', valor='-1')
        self.assertEqual(self.post('movimentos/', payload).status_code, 400)
        payload.update(valor='1', data=str(self.hoje + timedelta(days=1)))
        self.assertEqual(self.post('movimentos/', payload).status_code, 400)

    def test_periodo_e_capital_do_emprestimo_no_caixa(self):
        contrato = Contrato.objects.create(cliente=self.cliente, tipo=Contrato.Tipo.TRADICIONAL, data_inicio=self.hoje, valor_principal=1000)
        Parcela.objects.create(contrato=contrato, valor=200, data_vencimento=self.hoje, status='paga', data_pagamento=self.hoje, valor_pago=200)
        resumo = self.client.get('/api/operacoes/financeiro/').data
        self.assertEqual(resumo['capital_emprestado'], Decimal('1000'))
        self.assertEqual(resumo['recebido_emprestimos'], Decimal('200'))
        self.assertEqual(resumo['saldo_periodo'], Decimal('-800'))
        self.assertEqual(self.client.get('/api/operacoes/financeiro/?inicio=invalido').status_code, 400)

    def test_placa_normalizada_nao_aceita_duplicata(self):
        self.assertEqual(self.post('motos/', {'placa': 'abc-1d23', 'modelo': 'Duplicada'}).status_code, 400)

    def test_emprestimo_rejeita_principal_zero_e_parcelas_zero(self):
        payload = {'cliente': self.cliente.pk, 'tipo': 'emprestimo_tradicional', 'data_inicio': str(self.hoje), 'valor_principal': '1000', 'taxa_juros_mensal': '10', 'qtd_parcelas': 0, 'data_primeira_parcela': str(self.hoje)}
        self.assertEqual(self.client.post('/api/contratos/', payload, format='json').status_code, 400)
        payload.update(tipo='emprestimo_somente_juros', valor_principal='0', qtd_parcelas=None, valor_juros_mensal='100', dia_vencimento=10)
        self.assertEqual(self.client.post('/api/contratos/', payload, format='json').status_code, 400)


class ContratosPdfTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user('gestor-pdf'))
        self.cliente = Cliente.objects.create(nome='Cliente <Teste> & Cia', telefone='85988887777')

    def test_contrato_de_locacao_em_pdf(self):
        moto = Moto.objects.create(placa='ABC1D23', modelo='CG 160')
        hoje = date.today()
        resposta = self.client.post('/api/operacoes/alugueis/', dict(moto=moto.pk, cliente=self.cliente.pk, inicio=str(hoje), fim=str(hoje + timedelta(days=14)), valor='100.00', periodicidade='semanal', primeiro_vencimento=str(hoje)), format='json')
        pdf = self.client.get(f"/api/operacoes/alugueis/{resposta.data['id']}/contrato/")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        self.assertTrue(b''.join(pdf.streaming_content).startswith(b'%PDF'))
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"/api/operacoes/alugueis/{resposta.data['id']}/contrato/").status_code, 401)

    def test_contrato_de_mutuo_apenas_para_emprestimos(self):
        hoje = date.today()
        emprestimo = Contrato.objects.create(cliente=self.cliente, tipo='emprestimo_tradicional', data_inicio=hoje, valor_principal=Decimal('1000'), taxa_juros_mensal=Decimal('5'), qtd_parcelas=2, valor_parcela=Decimal('550'))
        Parcela.objects.create(contrato=emprestimo, numero=1, valor=Decimal('550'), data_vencimento=hoje)
        pdf = self.client.get(f'/api/contratos/{emprestimo.pk}/instrumento/')
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(b''.join(pdf.streaming_content).startswith(b'%PDF'))
        venda = Contrato.objects.create(cliente=self.cliente, tipo='venda', data_inicio=hoje, valor_venda=Decimal('500'))
        self.assertEqual(self.client.get(f'/api/contratos/{venda.pk}/instrumento/').status_code, 400)

    def test_valor_por_extenso(self):
        from core.pdf_contrato import extenso_reais
        self.assertEqual(extenso_reais('1234.56'), 'mil duzentos e trinta e quatro reais e cinquenta e seis centavos')
        self.assertEqual(extenso_reais('2000000'), 'dois milhões de reais')
        self.assertEqual(extenso_reais('1100'), 'mil e cem reais')
