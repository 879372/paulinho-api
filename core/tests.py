from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from .models import Cliente, ContaPagar, Contrato, MensagemEnviada, Parcela
from .api.contratos.services import gerar_parcelas_do_contrato
from .api.cobrancas.services import cobrancas_do_dia, gerar_juros_mensais
from .management.commands.enviar_lembretes_atraso import Command as LembretesAtrasoCommand
from .management.commands.enviar_cobrancas_do_dia import contas_vencendo_em, montar_resumo
from .whatsapp import enviar_whatsapp, normalizar_numero_whatsapp


class WhatsAppTests(TestCase):
    def test_normaliza_numero_brasileiro(self):
        self.assertEqual(normalizar_numero_whatsapp('(85) 99999-9999'), '5585999999999')

    @override_settings(
        EVOLUTION_API_URL='https://whatsapp.example.test',
        EVOLUTION_API_KEY='chave-teste',
        EVOLUTION_INSTANCE='gestao-testes',
    )
    @patch('core.whatsapp.requests.post')
    def test_envia_texto_pela_evolution_api(self, post):
        post.return_value = Mock(ok=True)
        post.return_value.json.return_value = {'key': {'id': 'mensagem-1'}}

        resultado = enviar_whatsapp('(85) 99999-9999', 'Olá!')

        post.assert_called_once_with(
            'https://whatsapp.example.test/message/sendText/gestao-testes',
            headers={'apikey': 'chave-teste'},
            json={
                'number': '5585999999999',
                'text': 'Olá!',
            },
            timeout=20,
        )
        self.assertEqual(resultado, {'key': {'id': 'mensagem-1'}})

class ContratoServiceTests(TestCase):
    def setUp(self): self.cliente = Cliente.objects.create(nome='Ana', telefone='85999999999')
    def test_venda_gera_parcelas_e_ajusta_arredondamento(self):
        contrato = Contrato.objects.create(cliente=self.cliente, tipo='venda', data_inicio=date.today(), valor_venda=Decimal('100.00'), qtd_parcelas=3, data_primeira_parcela=date.today())
        gerar_parcelas_do_contrato(contrato)
        self.assertEqual(contrato.parcelas.count(), 3)
        self.assertEqual(sum(p.valor for p in contrato.parcelas.all()), Decimal('100.00'))

    def test_venda_gera_vencimentos_semanais(self):
        contrato = Contrato.objects.create(cliente=self.cliente, tipo='venda', data_inicio=date(2026, 8, 1), valor_venda=Decimal('300.00'), qtd_parcelas=3, periodicidade='semanal', data_primeira_parcela=date(2026, 8, 10))
        gerar_parcelas_do_contrato(contrato)
        self.assertEqual(list(contrato.parcelas.values_list('data_vencimento', flat=True)), [date(2026, 8, 10), date(2026, 8, 17), date(2026, 8, 24)])

    def test_venda_gera_vencimentos_quinzenais(self):
        contrato = Contrato.objects.create(cliente=self.cliente, tipo='venda', data_inicio=date(2026, 8, 1), valor_venda=Decimal('300.00'), qtd_parcelas=3, periodicidade='quinzenal', data_primeira_parcela=date(2026, 8, 10))
        gerar_parcelas_do_contrato(contrato)
        self.assertEqual(list(contrato.parcelas.values_list('data_vencimento', flat=True)), [date(2026, 8, 10), date(2026, 8, 25), date(2026, 9, 9)])
    def test_juros_mensal_nao_duplica_mes(self):
        contrato = Contrato.objects.create(cliente=self.cliente, tipo='emprestimo_somente_juros', data_inicio=date.today(), valor_principal=Decimal('1000'), taxa_juros_mensal=Decimal('10'), valor_juros_mensal=Decimal('100'), dia_vencimento=10)
        gerar_juros_mensais(date(2026, 8, 1)); gerar_juros_mensais(date(2026, 8, 20))
        self.assertEqual(contrato.parcelas.count(), 1)

    def test_cobrancas_do_dia_prioriza_atrasadas_e_inclui_pendentes_de_hoje(self):
        contrato = Contrato.objects.create(
            cliente=self.cliente,
            tipo=Contrato.Tipo.VENDA,
            data_inicio=date.today(),
            valor_venda=Decimal('300.00'),
            qtd_parcelas=3,
            data_primeira_parcela=date.today(),
        )
        atrasada = Parcela.objects.create(
            contrato=contrato, numero=1, valor=Decimal('100.00'),
            data_vencimento=date.today() - timedelta(days=2), status=Parcela.Status.ATRASADA,
        )
        hoje = Parcela.objects.create(
            contrato=contrato, numero=2, valor=Decimal('100.00'),
            data_vencimento=date.today(), status=Parcela.Status.PENDENTE,
        )
        Parcela.objects.create(
            contrato=contrato, numero=3, valor=Decimal('100.00'),
            data_vencimento=date.today() + timedelta(days=1), status=Parcela.Status.PENDENTE,
        )

        self.assertEqual(list(cobrancas_do_dia().values_list('id', flat=True)), [atrasada.id, hoje.id])

    def test_lembrete_atraso_nao_duplica_no_mesmo_dia(self):
        contrato = Contrato.objects.create(
            cliente=self.cliente, tipo=Contrato.Tipo.VENDA, data_inicio=date.today(),
            valor_venda=Decimal('100.00'), qtd_parcelas=1, data_primeira_parcela=date.today(),
        )
        parcela = Parcela.objects.create(
            contrato=contrato, numero=1, valor=Decimal('100.00'),
            data_vencimento=date.today() - timedelta(days=1), status=Parcela.Status.ATRASADA,
        )
        with patch('core.management.commands.enviar_lembretes_atraso.enviar_whatsapp') as enviar:
            LembretesAtrasoCommand().handle()
            LembretesAtrasoCommand().handle()
        self.assertEqual(enviar.call_count, 1)
        self.assertEqual(MensagemEnviada.objects.filter(parcela=parcela, tipo=MensagemEnviada.Tipo.ATRASO).count(), 1)

    def test_resumo_do_proprietario_inclui_conta_sem_valor(self):
        conta = ContaPagar.objects.create(descricao='Internet da loja', dia_vencimento=date.today().day)
        resumo = montar_resumo([], [conta])
        self.assertIn('*CONTAS A PAGAR*', resumo)
        self.assertIn('Internet da loja', resumo)
        self.assertIn('Vence hoje', resumo)

    def test_conta_recorrente_dia_31_avisa_no_ultimo_dia_do_mes(self):
        conta = ContaPagar.objects.create(descricao='Aluguel', dia_vencimento=31)
        self.assertEqual(contas_vencendo_em(date(2026, 2, 28)), [conta])
        conta.ativa = False
        conta.save(update_fields=['ativa'])
        self.assertEqual(contas_vencendo_em(date(2026, 3, 31)), [])


class ApiRouteTests(TestCase):
    """Smoke tests dos contratos HTTP públicos definidos na spec."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='operador', password='senha-segura')
        self.client = APIClient()

    def autenticar(self):
        response = self.client.post('/api/auth/login/', {'username': 'operador', 'password': 'senha-segura'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def criar_cliente(self):
        response = self.client.post('/api/clientes/', {'nome': 'Maria Silva', 'telefone': '85999998888', 'cpf': '12345678909'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['id']

    def test_rotas_de_dados_exigem_jwt(self):
        for url in ['/api/clientes/', '/api/contratos/', '/api/parcelas/', '/api/contas-a-pagar/', '/api/comprovantes/gerar/', '/api/orcamentos/gerar/', '/api/cobrancas-do-dia/', '/api/dashboard/']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 401)

    def test_gera_comprovante_avulso_em_pdf(self):
        self.autenticar()
        response = self.client.post('/api/comprovantes/gerar/', {
            'cliente_nome': 'João da Silva',
            'produto': 'Samsung Galaxy A07',
            'valor_produto': '1500.00',
            'forma_pagamento': 'pix',
            'data_compra': '2026-08-26',
            'garantia': '3 meses',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('comprovante-compra.pdf', response['Content-Disposition'])
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF'))

    def test_gera_orcamento_misto_com_varios_itens_em_pdf(self):
        self.autenticar()
        response = self.client.post('/api/orcamentos/gerar/', {
            'cliente_nome': 'João da Silva',
            'data_emissao': '2026-09-02',
            'validade': '2026-09-09',
            'observacoes': 'Valores sujeitos à disponibilidade.',
            'itens': [
                {'tipo': 'servico', 'descricao': 'Troca de tela', 'quantidade': 2, 'valor_unitario': '300.00', 'garantia': '90 dias'},
                {'tipo': 'produto', 'descricao': 'iPhone Pro Max', 'quantidade': 1, 'forma_proposta': 'parcelado', 'valor_entrada': '500.00', 'qtd_parcelas': 10, 'valor_parcela': '500.00'},
                {'tipo': 'emprestimo_tradicional', 'valor_emprestado': '2000.00', 'taxa_juros_mensal': '15.000', 'qtd_parcelas': 10, 'valor_parcela': '200.00'},
                {'tipo': 'emprestimo_somente_juros', 'valor_emprestado': '2000.00', 'juros_mensal': '200.00', 'valor_quitacao': '2200.00'},
            ],
        }, format='json')
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('orcamento.pdf', response['Content-Disposition'])
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF'))

    def test_orcamento_rejeita_item_sem_campos_da_modalidade(self):
        self.autenticar()
        response = self.client.post('/api/orcamentos/gerar/', {
            'cliente_nome': 'João', 'data_emissao': '2026-09-02', 'validade': '2026-09-09',
            'itens': [{'tipo': 'servico', 'descricao': 'Troca de tela'}],
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_cadastra_e_encerra_conta_recorrente(self):
        self.autenticar()
        cadastro = self.client.post('/api/contas-a-pagar/', {
            'descricao': 'Energia da loja', 'dia_vencimento': 30,
        }, format='json')
        self.assertEqual(cadastro.status_code, 201, cadastro.data)
        encerramento = self.client.patch(f"/api/contas-a-pagar/{cadastro.data['id']}/", {'ativa': False}, format='json')
        self.assertEqual(encerramento.status_code, 200, encerramento.data)
        conta = ContaPagar.objects.get(pk=cadastro.data['id'])
        self.assertFalse(conta.ativa)
        self.assertIsNotNone(conta.encerrada_em)

    @override_settings(ALLOWED_HOSTS=['healthcheck.railway.app'], SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=[r'^api/health/$'])
    def test_healthcheck_publico_nao_redireciona_para_https(self):
        response = self.client.get('/api/health/', HTTP_HOST='healthcheck.railway.app')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_login_refresh_e_rotas_de_clientes(self):
        login = self.client.post('/api/auth/login/', {'username': 'operador', 'password': 'senha-segura'}, format='json')
        self.assertEqual(login.status_code, 200)
        self.assertIn('access', login.data)
        refresh = self.client.post('/api/auth/refresh/', {'refresh': login.data['refresh']}, format='json')
        self.assertEqual(refresh.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        cliente_id = self.criar_cliente()
        self.assertEqual(self.client.get('/api/clientes/').status_code, 200)
        self.assertEqual(self.client.get(f'/api/clientes/{cliente_id}/').status_code, 200)

    def test_cliente_nao_pode_repetir_telefone_com_outra_formatacao(self):
        self.autenticar()
        Cliente.objects.create(nome='Cliente existente', telefone='(84) 99999-8888')

        response = self.client.post('/api/clientes/', {
            'nome': 'Cliente duplicado', 'telefone': '+55 84 99999-8888',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['telefone'][0], 'Já existe um cliente cadastrado com este telefone.')
        self.assertEqual(Cliente.objects.filter(nome='Cliente duplicado').count(), 0)

    def test_cadastra_clientes_sem_cpf(self):
        self.autenticar()
        # Reproduz o registro legado que mantinha CPF opcional como texto vazio.
        Cliente.objects.create(nome='Cliente legado', telefone='84999990000', cpf='')

        response = self.client.post('/api/clientes/', {
            'nome': 'Cliente sem CPF', 'telefone': '84999990001', 'cpf': '',
        }, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(Cliente.objects.get(pk=response.data['id']).cpf)

    def test_atualiza_dados_do_cliente(self):
        self.autenticar()
        cliente_id = self.criar_cliente()

        response = self.client.patch(f'/api/clientes/{cliente_id}/', {
            'nome': 'Maria Souza',
            'telefone': '(84) 98888-7777',
            'cpf': '12345678909',
            'endereco': 'Rua das Flores, 120',
            'observacoes': 'Prefere contato pelo WhatsApp.',
        }, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['nome'], 'Maria Souza')
        self.assertEqual(response.data['telefone'], '84988887777')
        self.assertEqual(response.data['endereco'], 'Rua das Flores, 120')

    def test_detalhe_cliente_retorna_contratos_e_parcelas(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        contrato = Contrato.objects.create(
            cliente_id=cliente_id, tipo=Contrato.Tipo.VENDA, data_inicio=date.today(),
            produto='Smartphone', valor_venda=Decimal('500.00'), qtd_parcelas=2,
            data_primeira_parcela=date.today(),
        )
        gerar_parcelas_do_contrato(contrato)

        response = self.client.get(f'/api/clientes/{cliente_id}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['contratos'][0]['produto'], 'Smartphone')
        self.assertEqual(len(response.data['contratos'][0]['parcelas']), 2)

    def test_gera_relatorio_consolidado_do_cliente_em_pdf(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        contrato = Contrato.objects.create(
            cliente_id=cliente_id, tipo=Contrato.Tipo.TRADICIONAL, data_inicio=date.today(),
            valor_principal=Decimal('2000.00'), valor_parcela=Decimal('200.00'),
            qtd_parcelas=10, data_primeira_parcela=date.today(),
        )
        gerar_parcelas_do_contrato(contrato)

        response = self.client.get(f'/api/clientes/{cliente_id}/relatorio/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn(f'relatorio-cliente-{cliente_id}.pdf', response['Content-Disposition'])
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF'))

    def test_relatorio_somente_juros_separa_emprestado_juros_e_quitacao(self):
        from core.api.clientes.pdf import valor_emprestado_somente_juros, valor_quitacao

        cliente = Cliente.objects.create(nome='Eunice', telefone='84988887777')
        contrato = Contrato.objects.create(
            cliente=cliente, tipo=Contrato.Tipo.JUROS, data_inicio=date.today(),
            valor_principal=Decimal('2700.00'), valor_juros_mensal=Decimal('700.00'),
            taxa_juros_mensal=Decimal('25.926'), dia_vencimento=30,
        )

        self.assertEqual(valor_emprestado_somente_juros(contrato), Decimal('2000.00'))
        self.assertEqual(valor_quitacao(contrato), Decimal('2700.00'))

    def test_fluxo_venda_parcela_baixa_dashboard_e_pdf(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        contrato = self.client.post('/api/contratos/', {
            'cliente': cliente_id, 'tipo': 'venda', 'data_inicio': '2026-08-12',
            'produto': 'Notebook', 'valor_produto': '220.00', 'valor_venda': '300.00', 'teve_entrada': True,
            'valor_entrada': '30.00', 'qtd_parcelas': 3, 'periodicidade': 'mensal',
            'data_primeira_parcela': '2026-08-12',
        }, format='json')
        self.assertEqual(contrato.status_code, 201, contrato.data)
        contrato_id = contrato.data['id']
        detalhe = self.client.get(f'/api/contratos/{contrato_id}/')
        self.assertEqual(detalhe.status_code, 200)
        self.assertEqual(len(detalhe.data['parcelas']), 3)
        parcela_id = detalhe.data['parcelas'][0]['id']
        self.assertEqual(self.client.get('/api/parcelas/?vencimento=hoje').status_code, 200)
        baixa = self.client.patch(f'/api/parcelas/{parcela_id}/dar-baixa/', {'forma_pagamento': 'pix', 'valor_pago': '90.00'}, format='json')
        self.assertEqual(baixa.status_code, 200, baixa.data)
        self.assertEqual(baixa.data['status'], 'paga')
        cobrancas = self.client.get('/api/cobrancas-do-dia/?page_size=1')
        self.assertEqual(cobrancas.status_code, 200)
        self.assertIn('results', cobrancas.data)
        self.assertEqual(self.client.get('/api/dashboard/').status_code, 200)
        pdf = self.client.get(f'/api/contratos/{contrato_id}/comprovante/')
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')

    def test_desfaz_baixa_e_reabre_parcela_e_contrato(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        contrato = Contrato.objects.create(
            cliente_id=cliente_id, tipo=Contrato.Tipo.VENDA,
            data_inicio=date.today(), valor_venda=Decimal('100.00'),
            qtd_parcelas=1, data_primeira_parcela=date.today(),
            status=Contrato.Status.QUITADO,
        )
        parcela = Parcela.objects.create(
            contrato=contrato, numero=1, valor=Decimal('100.00'),
            data_vencimento=date.today(), status=Parcela.Status.PAGA,
            data_pagamento=date.today(), forma_pagamento=Parcela.Forma.PIX,
            valor_pago=Decimal('100.00'),
        )

        response = self.client.patch(f'/api/parcelas/{parcela.id}/desfazer-baixa/', format='json')

        self.assertEqual(response.status_code, 200, response.data)
        parcela.refresh_from_db()
        contrato.refresh_from_db()
        self.assertEqual(parcela.status, Parcela.Status.PENDENTE)
        self.assertIsNone(parcela.data_pagamento)
        self.assertIsNone(parcela.forma_pagamento)
        self.assertIsNone(parcela.valor_pago)
        self.assertEqual(contrato.status, Contrato.Status.ATIVO)

    def test_desfaz_baixa_vencida_e_marca_contrato_atrasado(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        contrato = Contrato.objects.create(
            cliente_id=cliente_id, tipo=Contrato.Tipo.TRADICIONAL,
            data_inicio=date.today(), valor_principal=Decimal('200.00'),
            qtd_parcelas=1, valor_parcela=Decimal('220.00'),
            data_primeira_parcela=date.today() - timedelta(days=1),
            status=Contrato.Status.QUITADO,
        )
        parcela = Parcela.objects.create(
            contrato=contrato, numero=1, valor=Decimal('220.00'),
            data_vencimento=date.today() - timedelta(days=1), status=Parcela.Status.PAGA,
            data_pagamento=date.today(), forma_pagamento=Parcela.Forma.DINHEIRO,
            valor_pago=Decimal('220.00'),
        )

        response = self.client.patch(f'/api/parcelas/{parcela.id}/desfazer-baixa/', format='json')

        self.assertEqual(response.status_code, 200, response.data)
        parcela.refresh_from_db()
        contrato.refresh_from_db()
        self.assertEqual(parcela.status, Parcela.Status.ATRASADA)
        self.assertEqual(contrato.status, Contrato.Status.ATRASADO)

    def test_dashboard_soma_apenas_parcelas_em_aberto_do_mes_atual(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        contrato = Contrato.objects.create(
            cliente_id=cliente_id, tipo=Contrato.Tipo.VENDA,
            data_inicio=date.today(), valor_venda=Decimal('900.00'),
            qtd_parcelas=3, data_primeira_parcela=date.today(),
        )
        Parcela.objects.create(
            contrato=contrato, numero=1, valor=Decimal('300.00'),
            data_vencimento=date.today() - timedelta(days=1), status=Parcela.Status.ATRASADA,
        )
        Parcela.objects.create(
            contrato=contrato, numero=2, valor=Decimal('300.00'),
            data_vencimento=date.today(), status=Parcela.Status.PENDENTE,
        )
        Parcela.objects.create(
            contrato=contrato, numero=3, valor=Decimal('300.00'),
            data_vencimento=date.today() + timedelta(days=30), status=Parcela.Status.PENDENTE,
        )

        response = self.client.get('/api/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data['a_receber']), Decimal('600.00'))

    def test_quitacao_principal_em_rota_propria(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        contrato = self.client.post('/api/contratos/', {
            'cliente': cliente_id, 'tipo': 'emprestimo_somente_juros', 'data_inicio': '2026-08-12',
            'valor_principal': '1000.00', 'taxa_juros_mensal': '10.000', 'valor_juros_mensal': '100.00',
            'dia_vencimento': 10,
        }, format='json')
        self.assertEqual(contrato.status_code, 201, contrato.data)
        quitacao = self.client.post(f"/api/contratos/{contrato.data['id']}/quitar-principal/", {'forma_pagamento': 'dinheiro'}, format='json')
        self.assertEqual(quitacao.status_code, 201, quitacao.data)
        self.assertEqual(quitacao.data['tipo'], 'quitacao_principal')
        self.assertEqual(Decimal(quitacao.data['valor_pago']), Decimal('1000.00'))
        self.assertFalse(Parcela.objects.filter(contrato_id=contrato.data['id'], tipo=Parcela.Tipo.JUROS, status__in=[Parcela.Status.PENDENTE, Parcela.Status.ATRASADA]).exists())

    def test_somente_juros_semanal_cobra_no_dia_da_semana(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        contrato = self.client.post('/api/contratos/', {
            'cliente': cliente_id, 'tipo': 'emprestimo_somente_juros', 'data_inicio': '2026-08-12',
            'valor_principal': '1000.00', 'taxa_juros_mensal': '10.000', 'valor_juros_mensal': '25.00',
            'periodicidade': 'semanal', 'dia_semana': 'sexta',
        }, format='json')
        self.assertEqual(contrato.status_code, 201, contrato.data)
        self.assertIsNone(contrato.data['dia_vencimento'])
        parcela = Parcela.objects.get(contrato_id=contrato.data['id'])
        self.assertEqual(parcela.data_vencimento.weekday(), 4)
        self.assertLess((parcela.data_vencimento - date.today()).days, 7)

        baixa = self.client.patch(f'/api/parcelas/{parcela.id}/dar-baixa/', {'forma_pagamento': 'pix', 'valor_pago': '25.00'}, format='json')
        self.assertEqual(baixa.status_code, 200, baixa.data)
        proxima = Parcela.objects.filter(contrato_id=contrato.data['id']).exclude(status=Parcela.Status.PAGA).get()
        self.assertEqual(proxima.data_vencimento, parcela.data_vencimento + timedelta(weeks=1))

        edicao = self.client.patch(f"/api/contratos/{contrato.data['id']}/editar/", {
            'valor_principal': '1000.00', 'taxa_juros_mensal': '10.000', 'valor_juros_mensal': '30.00',
            'periodicidade': 'semanal', 'dia_semana': 'segunda',
        }, format='json')
        self.assertEqual(edicao.status_code, 200, edicao.data)
        self.assertEqual(edicao.data['dia_semana'], 'segunda')
        proxima.refresh_from_db()
        self.assertEqual(proxima.data_vencimento.weekday(), 0)
        self.assertEqual(proxima.valor, Decimal('30.00'))

        mensal = self.client.patch(f"/api/contratos/{contrato.data['id']}/editar/", {
            'valor_principal': '1000.00', 'taxa_juros_mensal': '10.000', 'valor_juros_mensal': '100.00',
            'periodicidade': 'mensal', 'dia_vencimento': 15, 'dia_semana': 'segunda',
        }, format='json')
        self.assertEqual(mensal.status_code, 200, mensal.data)
        self.assertEqual((mensal.data['periodicidade'], mensal.data['dia_vencimento'], mensal.data['dia_semana']), ('mensal', 15, None))

    def test_venda_semanal_exige_vencimento_no_dia_escolhido_e_edicao_salva_dia(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        base = {'cliente': cliente_id, 'tipo': 'venda', 'data_inicio': '2026-08-01', 'produto': 'Celular', 'valor_venda': '300.00', 'qtd_parcelas': 3, 'periodicidade': 'semanal', 'dia_semana': 'quarta'}
        invalido = self.client.post('/api/contratos/', {**base, 'data_primeira_parcela': '2026-08-06'}, format='json')
        self.assertEqual(invalido.status_code, 400)
        contrato = self.client.post('/api/contratos/', {**base, 'data_primeira_parcela': '2026-08-05'}, format='json')
        self.assertEqual(contrato.status_code, 201, contrato.data)
        edicao = self.client.patch(f"/api/contratos/{contrato.data['id']}/editar/", {
            'qtd_parcelas': 3, 'valor_parcela': '100.00', 'periodicidade': 'semanal', 'dia_semana': 'sabado', 'proximo_vencimento': '2026-08-08',
        }, format='json')
        self.assertEqual(edicao.status_code, 200, edicao.data)
        self.assertEqual(edicao.data['dia_semana'], 'sabado')
        self.assertEqual([p['data_vencimento'] for p in edicao.data['parcelas']], ['2026-08-08', '2026-08-15', '2026-08-22'])

    def test_emprestimo_tradicional_semanal_gera_parcelas_no_dia_escolhido(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        contrato = self.client.post('/api/contratos/', {
            'cliente': cliente_id, 'tipo': 'emprestimo_tradicional', 'data_inicio': '2026-08-01',
            'valor_principal': '1000.00', 'taxa_juros_mensal': '5.000', 'qtd_parcelas': 4,
            'periodicidade': 'semanal', 'dia_semana': 'segunda', 'data_primeira_parcela': '2026-08-03',
        }, format='json')
        self.assertEqual(contrato.status_code, 201, contrato.data)
        self.assertEqual(contrato.data['dia_semana'], 'segunda')
        vencimentos = list(Parcela.objects.filter(contrato_id=contrato.data['id']).order_by('numero').values_list('data_vencimento', flat=True))
        self.assertEqual(vencimentos, [date(2026, 8, 3), date(2026, 8, 10), date(2026, 8, 17), date(2026, 8, 24)])

    def test_concluir_contrato_remove_abertas_e_preserva_historico_pago(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        contrato = Contrato.objects.create(
            cliente_id=cliente_id, tipo=Contrato.Tipo.VENDA,
            data_inicio=date.today(), valor_venda=Decimal('200.00'),
            qtd_parcelas=2, data_primeira_parcela=date.today(),
        )
        paga = Parcela.objects.create(
            contrato=contrato, numero=1, valor=Decimal('100.00'),
            data_vencimento=date.today(), status=Parcela.Status.PAGA,
            data_pagamento=date.today(), forma_pagamento=Parcela.Forma.PIX,
            valor_pago=Decimal('100.00'),
        )
        aberta = Parcela.objects.create(
            contrato=contrato, numero=2, valor=Decimal('100.00'),
            data_vencimento=date.today(), status=Parcela.Status.PENDENTE,
        )

        response = self.client.post(f'/api/contratos/{contrato.id}/concluir/', format='json')

        self.assertEqual(response.status_code, 200, response.data)
        contrato.refresh_from_db()
        self.assertEqual(contrato.status, Contrato.Status.QUITADO)
        self.assertTrue(Parcela.objects.filter(pk=paga.pk).exists())
        self.assertFalse(Parcela.objects.filter(pk=aberta.pk).exists())

    def test_excluir_contrato_remove_parcelas(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        contrato = Contrato.objects.create(
            cliente_id=cliente_id, tipo=Contrato.Tipo.VENDA,
            data_inicio=date.today(), valor_venda=Decimal('100.00'),
            qtd_parcelas=1, data_primeira_parcela=date.today(),
        )
        parcela = Parcela.objects.create(
            contrato=contrato, numero=1, valor=Decimal('100.00'),
            data_vencimento=date.today(),
        )

        response = self.client.delete(f'/api/contratos/{contrato.id}/excluir/')

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Contrato.objects.filter(pk=contrato.pk).exists())
        self.assertFalse(Parcela.objects.filter(pk=parcela.pk).exists())

    @patch('core.api.contratos.services.date')
    def test_somente_juros_preserva_taxa_e_valor_independentes_e_gera_proxima(self, data_atual):
        data_atual.today.return_value = date(2026, 8, 12)
        data_atual.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
        self.autenticar()
        cliente_id = self.criar_cliente()
        response = self.client.post('/api/contratos/', {
            'cliente': cliente_id, 'tipo': 'emprestimo_somente_juros',
            'data_inicio': '2026-08-12', 'valor_principal': '2000.00',
            'taxa_juros_mensal': '7.000', 'valor_juros_mensal': '200.00',
            'dia_vencimento': 10,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        contrato = Contrato.objects.get(pk=response.data['id'])
        self.assertEqual(contrato.taxa_juros_mensal, Decimal('7.000'))
        self.assertIsNone(contrato.qtd_parcelas)
        primeira = contrato.parcelas.get()
        self.assertEqual((primeira.valor, primeira.data_vencimento), (Decimal('200.00'), date(2026, 9, 10)))
        baixa = self.client.patch(f'/api/parcelas/{primeira.id}/dar-baixa/', {
            'forma_pagamento': 'pix', 'valor_pago': '200.00', 'data_pagamento': '2026-09-10',
        }, format='json')
        self.assertEqual(baixa.status_code, 200, baixa.data)
        proxima = contrato.parcelas.exclude(pk=primeira.pk).get()
        self.assertEqual((proxima.valor, proxima.data_vencimento, proxima.status), (Decimal('200.00'), date(2026, 10, 10), Parcela.Status.PENDENTE))

    def test_edita_contrato_somente_juros_sem_alterar_cobrancas_pagas(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        response = self.client.post('/api/contratos/', {
            'cliente': cliente_id, 'tipo': 'emprestimo_somente_juros',
            'data_inicio': '2026-08-12', 'valor_principal': '2000.00',
            'taxa_juros_mensal': '7.000', 'valor_juros_mensal': '200.00',
            'dia_vencimento': 10,
        }, format='json')
        contrato = Contrato.objects.get(pk=response.data['id'])
        aberta = contrato.parcelas.get()
        edicao = self.client.patch(f'/api/contratos/{contrato.id}/editar/', {
            'valor_principal': '2500.00', 'taxa_juros_mensal': '8.000',
            'valor_juros_mensal': '250.00', 'dia_vencimento': 20,
            'observacoes': 'Contrato atualizado',
        }, format='json')
        self.assertEqual(edicao.status_code, 200, edicao.data)
        contrato.refresh_from_db()
        aberta.refresh_from_db()
        self.assertEqual((contrato.valor_principal, contrato.taxa_juros_mensal, contrato.valor_juros_mensal), (Decimal('2500.00'), Decimal('8.000'), Decimal('250.00')))
        self.assertEqual((aberta.valor, aberta.data_vencimento.day), (Decimal('250.00'), 20))

    def test_listagens_possuem_paginacao_e_filtros(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        for numero in range(3):
            contrato = Contrato.objects.create(
                cliente_id=cliente_id, tipo=Contrato.Tipo.VENDA, data_inicio=date.today(),
                produto=f'Produto {numero}', valor_venda=Decimal('100.00'), qtd_parcelas=1,
                data_primeira_parcela=date.today(),
            )
            gerar_parcelas_do_contrato(contrato)
        clientes = self.client.get('/api/clientes/?busca=Maria&page_size=1')
        self.assertEqual(clientes.status_code, 200)
        self.assertEqual(clientes.data['count'], 1)
        self.assertEqual(len(clientes.data['results']), 1)
        contratos = self.client.get('/api/contratos/?tipo=venda&page_size=2')
        self.assertEqual(contratos.status_code, 200)
        self.assertEqual(contratos.data['count'], 3)
        self.assertIsNotNone(contratos.data['next'])
        parcelas = self.client.get('/api/parcelas/?busca=Maria&vencimento=hoje&page_size=2')
        self.assertEqual(parcelas.status_code, 200)
        self.assertEqual(parcelas.data['count'], 3)
        self.assertEqual(len(parcelas.data['results']), 2)

    def test_venda_calcula_parcela_a_partir_do_valor_da_venda(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        response = self.client.post('/api/contratos/', {
            'cliente': cliente_id, 'tipo': 'venda', 'produto': 'iPhone 13',
            'valor_produto': '1800.00', 'valor_venda': '2500.00',
            'teve_entrada': True, 'valor_entrada': '500.00', 'qtd_parcelas': 10,
            'calcular_por': 'valor_venda', 'periodicidade': 'mensal',
            'data_inicio': '2026-08-12', 'data_primeira_parcela': '2026-09-12',
            'observacoes': 'Garantia de 90 dias.',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        contrato = Contrato.objects.get(pk=response.data['id'])
        self.assertEqual(contrato.valor_parcela, Decimal('200.00'))
        self.assertEqual(contrato.parcelas.count(), 10)
        self.assertEqual(contrato.observacoes, 'Garantia de 90 dias.')

    def test_contrato_novo_permite_venda_sem_valor_de_compra(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        response = self.client.post('/api/contratos/', {
            'cliente': cliente_id, 'origem': 'novo', 'tipo': 'venda',
            'produto': 'iPhone 13', 'valor_venda': '2500.00',
            'teve_entrada': False, 'qtd_parcelas': 10,
            'calcular_por': 'valor_venda', 'periodicidade': 'mensal',
            'data_inicio': '2026-08-12', 'data_primeira_parcela': '2026-09-12',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(Contrato.objects.get(pk=response.data['id']).valor_produto)

    def test_contrato_importado_permite_venda_sem_valor_de_compra(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        response = self.client.post('/api/contratos/', {
            'cliente': cliente_id, 'origem': 'importado', 'tipo': 'venda',
            'produto': 'iPhone usado', 'valor_venda': '1200.00',
            'teve_entrada': False, 'qtd_parcelas': 6,
            'calcular_por': 'valor_venda', 'periodicidade': 'mensal',
            'data_inicio': '2026-01-10', 'data_primeira_parcela': '2026-02-10',
            'qtd_parcelas_pagas': 0,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(Contrato.objects.get(pk=response.data['id']).valor_produto)

    def test_venda_calcula_total_a_partir_do_valor_da_parcela(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        response = self.client.post('/api/contratos/', {
            'cliente': cliente_id, 'tipo': 'venda', 'produto': 'Galaxy S24',
            'valor_produto': '2000.00', 'valor_parcela': '300.00',
            'teve_entrada': True, 'valor_entrada': '400.00', 'qtd_parcelas': 8,
            'calcular_por': 'valor_parcela', 'periodicidade': 'mensal',
            'data_inicio': '2026-08-12', 'data_primeira_parcela': '2026-09-12',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        contrato = Contrato.objects.get(pk=response.data['id'])
        self.assertEqual(contrato.valor_venda, Decimal('2800.00'))
        self.assertEqual(contrato.valor_parcela, Decimal('300.00'))

    def test_emprestimo_tradicional_calcula_taxa_e_parcela_nos_dois_sentidos(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        por_taxa = self.client.post('/api/contratos/', {
            'cliente': cliente_id, 'tipo': 'emprestimo_tradicional',
            'data_inicio': '2026-08-12', 'valor_principal': '1000.00',
            'taxa_juros_mensal': '10.000', 'qtd_parcelas': 10,
            'calcular_emprestimo_por': 'taxa', 'data_primeira_parcela': '2026-09-12',
        }, format='json')
        self.assertEqual(por_taxa.status_code, 201, por_taxa.data)
        self.assertEqual(Contrato.objects.get(pk=por_taxa.data['id']).valor_parcela, Decimal('200.00'))

        por_parcela = self.client.post('/api/contratos/', {
            'cliente': cliente_id, 'tipo': 'emprestimo_tradicional',
            'data_inicio': '2026-08-12', 'valor_principal': '1000.00',
            'valor_parcela': '150.00', 'qtd_parcelas': 10,
            'calcular_emprestimo_por': 'valor_parcela', 'data_primeira_parcela': '2026-09-12',
        }, format='json')
        self.assertEqual(por_parcela.status_code, 201, por_parcela.data)
        contrato = Contrato.objects.get(pk=por_parcela.data['id'])
        self.assertEqual((contrato.taxa_juros_mensal, contrato.valor_parcela), (Decimal('5.000'), Decimal('150.00')))

    def test_importacao_marca_historico_e_classifica_parcelas(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        response = self.client.post('/api/contratos/', {
            'cliente': cliente_id, 'origem': 'importado', 'tipo': 'venda',
            'produto': 'iPhone usado', 'valor_produto': '900.00', 'valor_venda': '1200.00',
            'teve_entrada': False, 'qtd_parcelas': 6, 'calcular_por': 'valor_venda',
            'periodicidade': 'mensal', 'data_inicio': '2026-01-10',
            'data_primeira_parcela': '2026-02-10', 'qtd_parcelas_pagas': 3,
            'data_ultimo_pagamento': '2026-04-10', 'forma_pagamento_historico': 'pix',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        contrato = Contrato.objects.get(pk=response.data['id'])
        self.assertEqual(contrato.origem, Contrato.Origem.IMPORTADO)
        self.assertEqual(contrato.parcelas.filter(status=Parcela.Status.PAGA).count(), 3)
        self.assertEqual(contrato.parcelas.get(numero=3).data_pagamento.isoformat(), '2026-04-10')

    def test_parcelas_aceitam_multiplos_status_e_periodo(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        contrato = Contrato.objects.create(cliente_id=cliente_id, tipo=Contrato.Tipo.VENDA, data_inicio=date.today(), produto='Celular azul', valor_venda=Decimal('200'), qtd_parcelas=2, data_primeira_parcela=date.today())
        gerar_parcelas_do_contrato(contrato)
        contrato.parcelas.filter(numero=1).update(status=Parcela.Status.ATRASADA)
        response = self.client.get(f'/api/parcelas/?status=atrasada,pendente&vencimento_de={date.today()}&vencimento_ate={date.today()}&busca=azul')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_edicao_do_contrato_altera_abertas_e_preserva_pagas(self):
        self.autenticar()
        cliente_id = self.criar_cliente()
        contrato = Contrato.objects.create(cliente_id=cliente_id, tipo=Contrato.Tipo.VENDA, data_inicio=date.today(), produto='Celular', valor_venda=Decimal('300'), qtd_parcelas=3, data_primeira_parcela=date(2026, 9, 10))
        gerar_parcelas_do_contrato(contrato)
        primeira, segunda, terceira = contrato.parcelas.order_by('numero')
        terceira.status = Parcela.Status.PAGA
        terceira.data_pagamento = date(2026, 10, 10)
        terceira.forma_pagamento = Parcela.Forma.PIX
        terceira.valor_pago = terceira.valor
        terceira.save()

        response = self.client.patch(f'/api/contratos/{contrato.id}/editar/', {
            'produto': 'Celular editado', 'valor_entrada': '50.00', 'valor_parcela': '120.00', 'qtd_parcelas': 4,
            'periodicidade': 'quinzenal', 'proximo_vencimento': '2026-10-15',
            'observacoes': 'Contrato renegociado.',
        }, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        segunda.refresh_from_db(); terceira.refresh_from_db(); primeira.refresh_from_db()
        self.assertEqual((primeira.valor, primeira.data_vencimento), (Decimal('120.00'), date(2026, 10, 15)))
        self.assertEqual((segunda.valor, segunda.data_vencimento), (Decimal('120.00'), date(2026, 10, 30)))
        self.assertEqual(terceira.valor, Decimal('100.00'))
        self.assertEqual(terceira.status, Parcela.Status.PAGA)
        contrato.refresh_from_db()
        self.assertEqual((contrato.produto, contrato.valor_entrada, contrato.teve_entrada, contrato.qtd_parcelas, contrato.valor_venda, contrato.observacoes), ('Celular editado', Decimal('50.00'), True, 4, Decimal('510.00'), 'Contrato renegociado.'))
        self.assertEqual(contrato.parcelas.count(), 4)
