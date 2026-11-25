from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from core.models import Cliente, Contrato, Parcela
from .models import Aluguel, Moto, Movimento, CobrancaAluguel


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


from unittest import mock
import json as _json
import re as _re
from django.test import override_settings


class _Resposta:
    def __init__(self, dados, status_code=200):
        self.status_code, self._dados, self.ok = status_code, dados, status_code < 400

    def json(self):
        return self._dados


class AssinaturaAutentiqueTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user('gestor-assinatura'))
        self.cliente = Cliente.objects.create(nome='Cliente Assina', telefone='85988887777')
        hoje = date.today()
        moto = Moto.objects.create(placa='TST1A23', modelo='CG 160')
        self.contrato = Aluguel.objects.create(moto=moto, cliente=self.cliente, inicio=hoje, fim=hoje+timedelta(days=30), valor=Decimal('250'), periodicidade='semanal', primeiro_vencimento=hoje)
        CobrancaAluguel.objects.create(aluguel=self.contrato, vencimento=hoje, valor=Decimal('250'))
        self.url = f'/api/operacoes/alugueis/{self.contrato.pk}/assinatura/'


    @override_settings(AUTENTIQUE_TOKEN='')
    def test_sem_token_informa_configuracao(self):
        resposta = self.client.post(self.url)
        self.assertEqual(resposta.status_code, 400)
        self.assertIn('AUTENTIQUE_TOKEN', resposta.data['detail'])
        self.assertFalse(self.client.get(self.url).data['configurado'])

    @override_settings(AUTENTIQUE_TOKEN='token-teste', AUTENTIQUE_SANDBOX=True, AUTENTIQUE_EMAIL_EMPRESA='')
    def test_envia_por_whatsapp_e_atualiza_status(self):
        criado = {'data': {'createDocument': {'id': 'doc-1', 'signatures': [
            {'name': 'Cliente Assina', 'email': None, 'action': {'name': 'SIGN'}, 'link': None},
            {'name': 'Gestão de Operações', 'email': None, 'action': {'name': 'SIGN'}, 'link': {'short_link': 'https://assina.ae/empresa'}}]}}}
        with mock.patch('core.assinatura.requests.post', return_value=_Resposta(criado)) as post:
            resposta = self.client.post(self.url)
        self.assertEqual(resposta.status_code, 201, resposta.data)
        operacoes = _json.loads(post.call_args.kwargs['data']['operations'])
        self.assertIn('sandbox: true', operacoes['query'])
        cliente = operacoes['variables']['signers'][0]
        self.assertEqual((cliente['phone'], cliente['delivery_method']), ('+5585988887777', 'DELIVERY_METHOD_WHATSAPP'))
        pdf = post.call_args.kwargs['files']['file'][1]
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertLessEqual(len(_re.findall(rb'/Type /Page[^s]', pdf)), 2)
        self.contrato.refresh_from_db()
        self.assertEqual((self.contrato.assinatura_status, self.contrato.assinatura_link_empresa), ('pendente', 'https://assina.ae/empresa'))
        self.assertEqual(self.client.post(self.url).status_code, 400)  # não reenvia sem pedido explícito

        assinado = {'data': {'document': {'id': 'doc-1', 'files': {'signed': 'https://x/assinado.pdf'}, 'signatures': [
            {'name': 'Cliente Assina', 'action': {'name': 'SIGN'}, 'signed': {'created_at': '2026-11-25'}, 'rejected': None},
            {'name': 'Gestão de Operações', 'action': {'name': 'SIGN'}, 'signed': {'created_at': '2026-11-25'}, 'rejected': None}]}}}
        with mock.patch('core.assinatura.requests.post', return_value=_Resposta(assinado)):
            resposta = self.client.get(self.url)
        self.assertEqual(resposta.data['assinatura_status'], 'assinado')
        self.assertTrue(all(s['assinou'] for s in resposta.data['signatarios']))

    @override_settings(AUTENTIQUE_TOKEN='token-teste')
    def test_erro_da_api_vira_mensagem(self):
        with mock.patch('core.assinatura.requests.post', return_value=_Resposta({'errors': [{'message': 'quota exceeded'}]})):
            resposta = self.client.post(self.url)
        self.assertEqual(resposta.status_code, 502)
        self.assertIn('quota exceeded', resposta.data['detail'])

    def test_locacao_longa_cabe_em_duas_paginas(self):
        from operacoes.contrato_pdf import contrato_locacao_bytes
        moto = Moto.objects.create(placa='XYZ1A23', modelo='CG 160')
        aluguel = Aluguel.objects.create(moto=moto, cliente=self.cliente, inicio=date.today(), fim=date.today() + timedelta(days=364), valor=Decimal('250'), periodicidade='semanal', primeiro_vencimento=date.today())
        for i in range(52):
            CobrancaAluguel.objects.create(aluguel=aluguel, vencimento=date.today() + timedelta(days=7 * i), valor=Decimal('250'))
        self.assertLessEqual(len(_re.findall(rb'/Type /Page[^s]', contrato_locacao_bytes(aluguel))), 2)


class DisponibilidadeMotoTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user('frota-teste'))
        self.cliente = Cliente.objects.create(nome='Cliente', telefone='85988887777')
        self.moto = Moto.objects.create(placa='ABC1D23', modelo='CG 160')

    def test_disponibilidade_acompanha_periodo_e_preserva_manutencao(self):
        from unittest.mock import patch
        inicio = date(2026, 11, 25)
        fim = inicio + timedelta(days=7)
        Aluguel.objects.create(moto=self.moto, cliente=self.cliente, inicio=inicio, fim=fim, primeiro_vencimento=inicio, periodicidade='semanal', valor='100')
        for dia, esperado in [(inicio-timedelta(days=1), 'disponivel'), (inicio, 'alugada'), (fim, 'alugada'), (fim+timedelta(days=1), 'disponivel')]:
            with self.subTest(dia=dia), patch('operacoes.views.timezone.localdate', return_value=dia):
                response = self.client.get('/api/operacoes/motos/')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data['results'][0]['disponibilidade'], esperado)
        self.moto.em_manutencao = True
        self.moto.save(update_fields=['em_manutencao'])
        with patch('operacoes.views.timezone.localdate', return_value=inicio):
            self.assertEqual(self.client.get('/api/operacoes/motos/').data['results'][0]['disponibilidade'], 'manutencao')


class CobrancasAluguelTests(TestCase):
    setUp = OperacoesTests.setUp
    aluguel = OperacoesTests.aluguel
    post = OperacoesTests.post
    def test_lista_filtra_busca_status_e_registra_recebimento(self):
        from unittest.mock import patch
        aluguel = self.aluguel()
        self.assertEqual(aluguel.status_code, 201)
        url = '/api/operacoes/alugueis/cobrancas/'
        with patch('operacoes.views.timezone.localdate', return_value=self.hoje), patch('operacoes.serializers.timezone.localdate', return_value=self.hoje):
            pendentes = self.client.get(url, {'status': 'pendente', 'busca': self.moto.placa})
            self.assertEqual(pendentes.data['count'], 3)
            item = pendentes.data['results'][0]
            self.assertEqual(item['status'], 'pendente')
            self.assertEqual(item['valor'], '100.00')
            self.assertEqual(self.client.get(url, {'busca': 'inexistente'}).data['count'], 0)
            self.assertEqual(self.client.get(url, {'status': 'paga'}).data['count'], 0)
            resposta = self.post(f"alugueis/cobrancas/{item['id']}/receber/", {'data': str(self.hoje)})
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(self.client.get(url, {'status': 'paga'}).data['count'], 1)
            self.assertEqual(Movimento.objects.filter(cobranca_id=item['id']).count(), 1)
        with patch('operacoes.views.timezone.localdate', return_value=self.hoje + timedelta(days=8)), patch('operacoes.serializers.timezone.localdate', return_value=self.hoje + timedelta(days=8)):
            atrasadas = self.client.get(url, {'status': 'atrasada'})
            self.assertEqual(atrasadas.data['count'], 1)
            self.assertEqual(atrasadas.data['results'][0]['status'], 'atrasada')
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_baixar_contrato_nao_envia_para_autentique(self):
        from unittest.mock import patch
        aluguel = self.aluguel()
        with patch('core.assinatura.requests.post') as enviar:
            pdf = self.client.get(f"/api/operacoes/alugueis/{aluguel.data['id']}/contrato/")
            self.assertEqual(pdf.status_code, 200)
            self.assertEqual(pdf['Content-Type'], 'application/pdf')
            self.assertIn('attachment', pdf['Content-Disposition'])
            enviar.assert_not_called()
        objeto = Aluguel.objects.get(pk=aluguel.data['id'])
        self.assertFalse(objeto.assinatura_id)


class CategoriasFinanceirasTests(TestCase):
    setUp = OperacoesTests.setUp
    post = OperacoesTests.post
    aluguel = OperacoesTests.aluguel

    def test_categoria_manual_e_automatica_conferem_com_caixa(self):
        for categoria, tipo, valor in [('emprestimos', 'entrada', '25'), ('motos', 'saida', '20'), ('animais', 'entrada', '50'), ('outros', 'saida', '5')]:
            resposta = self.post('movimentos/', {'descricao': categoria, 'categoria': categoria, 'tipo': tipo, 'valor': valor, 'data': str(self.hoje)})
            self.assertEqual(resposta.status_code, 201, resposta.data)
        cobranca = self.aluguel().data['cobrancas'][0]['id']
        self.assertEqual(self.post(f'alugueis/cobrancas/{cobranca}/receber/', {'data': str(self.hoje)}).status_code, 200)
        contrato = Contrato.objects.create(cliente=self.cliente, tipo='emprestimo_tradicional', origem='novo', data_inicio=self.hoje, valor_principal='200')
        Parcela.objects.create(contrato=contrato, numero=1, valor='40', valor_pago='40', data_vencimento=self.hoje, data_pagamento=self.hoje, status='paga')
        resumo = self.client.get('/api/operacoes/financeiro/').data
        grupos = {item['categoria']: item for item in resumo['categorias']}
        self.assertEqual(grupos['emprestimos']['entradas'], Decimal('65'))
        self.assertEqual(grupos['emprestimos']['saidas'], Decimal('200'))
        self.assertEqual(grupos['motos']['entradas'], Decimal('100'))
        self.assertEqual(grupos['motos']['saidas'], Decimal('20'))
        self.assertEqual(grupos['animais']['entradas'], Decimal('50'))
        self.assertEqual(resumo['entradas'], sum(item['entradas'] for item in grupos.values()))
        self.assertEqual(resumo['saldo_periodo'], sum(item['saldo'] for item in grupos.values()))
        self.assertEqual(len(resumo['lancamentos']), 7)
        ids = [item['id'] for item in resumo['lancamentos']]
        self.assertEqual(len(ids), len(set(ids)))
        fora = self.client.get('/api/operacoes/financeiro/', {'inicio': str(self.hoje-timedelta(days=2)), 'fim': str(self.hoje-timedelta(days=1))}).data
        self.assertEqual(fora['entradas'], 0)
        self.assertEqual(fora['saidas'], 0)
        self.assertEqual(fora['lancamentos'], [])


class AssinaturaEmprestimoDesativadaTests(TestCase):
    @override_settings(AUTENTIQUE_TOKEN='teste')
    def test_api_nao_envia_emprestimos_para_assinatura(self):
        client = APIClient()
        client.force_authenticate(get_user_model().objects.create_user('emprestimo-sem-assinatura'))
        cliente = Cliente.objects.create(nome='Cliente', telefone='84999990000')
        contrato = Contrato.objects.create(cliente=cliente, tipo='emprestimo_tradicional', data_inicio=date.today(), valor_principal=Decimal('100'))
        with mock.patch('core.assinatura.requests.post') as enviar:
            response = client.post(f'/api/contratos/{contrato.pk}/assinatura/')
            self.assertEqual(response.status_code, 405)
            self.assertFalse(client.get(f'/api/contratos/{contrato.pk}/assinatura/').data['configurado'])
            enviar.assert_not_called()


class CaucaoAluguelTests(TestCase):
    setUp = OperacoesTests.setUp
    post = OperacoesTests.post
    aluguel = OperacoesTests.aluguel

    def test_cadastra_caucao_sem_cobrar_ou_lancar_receita(self):
        resposta=self.aluguel(valor_caucao='500.00')
        self.assertEqual(resposta.status_code,201,resposta.data)
        self.assertEqual(resposta.data['valor_caucao'],'500.00')
        self.assertEqual(len(resposta.data['cobrancas']),3)
        self.assertTrue(all(item['valor']=='100.00' for item in resposta.data['cobrancas']))
        self.assertEqual(Movimento.objects.count(),0)

    def test_informa_caucao_em_aluguel_existente_e_permite_sem_caucao(self):
        resposta=self.aluguel()
        self.assertIsNone(resposta.data['valor_caucao'])
        url=f"/api/operacoes/alugueis/{resposta.data['id']}/caucao/"
        editar=self.client.patch(url,{'valor_caucao':'250.00'})
        self.assertEqual(editar.status_code,200,editar.data)
        self.assertEqual(editar.data['valor_caucao'],'250.00')
        self.assertEqual(self.client.patch(url,{'valor_caucao':'0.00'}).data['valor_caucao'],'0.00')
        self.assertEqual(Movimento.objects.count(),0)

    def test_rejeita_negativo_e_preserva_contrato_enviado_para_assinatura(self):
        self.assertEqual(self.aluguel(valor_caucao='-1').status_code,400)
        resposta=self.aluguel(valor_caucao='100')
        aluguel=Aluguel.objects.get(pk=resposta.data['id'])
        aluguel.assinatura_status='pendente';aluguel.save()
        url=f'/api/operacoes/alugueis/{aluguel.pk}/caucao/'
        self.assertEqual(self.client.patch(url,{'valor_caucao':'200'}).status_code,400)
        aluguel.refresh_from_db()
        self.assertEqual(aluguel.valor_caucao,Decimal('100'))
        self.client.force_authenticate(None)
        self.assertEqual(self.client.patch(url,{'valor_caucao':'200'}).status_code,401)
