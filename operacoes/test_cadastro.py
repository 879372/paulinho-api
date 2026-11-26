from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from core.models import Cliente
from .models import Moto, Aluguel
from .cadastro import cadastro_completo


def dados_validos():
    return dict(nome='Pessoa de Exemplo',cpf='52998224725',rg='1234567',orgao_emissor='ITEP/RN',nacionalidade='Brasileira',estado_civil='solteiro',profissao='Autônomo',telefone='84999990000',cnh_numero='12345678901',cnh_categoria='AB',cnh_validade=str(timezone.localdate()+timedelta(days=365)),cep='59000000',logradouro='Rua de Exemplo',numero='100',complemento='',bairro='Centro',cidade='Natal',uf='RN',confirmacao=True)


@override_settings(AUTENTIQUE_TOKEN='token-teste')
class CadastroLocatarioTests(TestCase):
    def setUp(self):
        self.client=APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user('cadastro'))
        self.publico=APIClient(enforce_csrf_checks=True)
        self.cliente=Cliente.objects.create(nome='Cadastro do Operador',telefone='84999990000')
        moto=Moto.objects.create(placa='ABC1D23',modelo='CG 160')
        hoje=timezone.localdate()
        self.aluguel=Aluguel.objects.create(cliente=self.cliente,moto=moto,inicio=hoje,fim=hoje+timedelta(days=30),valor=250,periodicidade='semanal',primeiro_vencimento=hoje)
        self.rota=f'/api/operacoes/alugueis/{self.aluguel.pk}'

    def gerar(self):
        result=self.client.post(self.rota+'/cadastro/',{},format='json')
        self.assertEqual(result.status_code,201,result.data)
        return result.data['token']

    def concluir(self,token,dados=None):
        return self.publico.post('/api/operacoes/cadastro-publico/concluir/',{'token':token,'dados':dados if dados is not None else dados_validos()},format='json')

    def test_bloqueia_assinatura_e_nao_expoe_dados_ou_token_na_lista(self):
        with patch('core.assinatura.requests.post') as enviar:
            result=self.client.post(self.rota+'/assinatura/',{},format='json')
            self.assertEqual(result.status_code,400)
            self.assertIn('formulário',result.data['detail'])
            enviar.assert_not_called()
        token=self.gerar()
        self.aluguel.refresh_from_db()
        self.assertNotEqual(self.aluguel.cadastro_token_hash,token)
        result=self.client.get('/api/operacoes/alugueis/').data['results'][0]
        self.assertNotIn('cadastro_token_hash',result)
        self.assertNotIn('dados_locatario',result)
        self.assertFalse(result['cadastro_completo'])

    def test_publico_preenche_sem_login_nao_envia_assinatura_e_nao_altera_cliente(self):
        token=self.gerar()
        with patch('core.assinatura.requests.post') as enviar:
            result=self.concluir(token)
            self.assertEqual(result.status_code,200,result.data)
            enviar.assert_not_called()
        self.aluguel.refresh_from_db()
        self.assertTrue(cadastro_completo(self.aluguel))
        self.assertEqual(self.aluguel.dados_locatario['cpf'],'52998224725')
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nome,'Cadastro do Operador')
        self.assertTrue(self.client.get(self.rota+'/assinatura/').data['cadastro_completo'])
        result=self.publico.post('/api/operacoes/cadastro-publico/consultar/',{'token':token},format='json')
        self.assertTrue(result.data['concluido'])
        self.assertNotIn('cpf',str(result.data))
        self.assertNotIn('dados_locatario',result.data)
        self.assertEqual(self.concluir(token).status_code,409)

    def test_rejeita_incompletos_cpf_invalido_e_cnh_vencida(self):
        token=self.gerar()
        self.assertEqual(self.concluir(token,{'nome':'Sem Dados'}).status_code,400)
        dados=dados_validos();dados['cpf']='11111111111'
        self.assertEqual(self.concluir(token,dados).status_code,400)
        dados=dados_validos();dados['cnh_validade']=str(timezone.localdate()-timedelta(days=1))
        self.assertEqual(self.concluir(token,dados).status_code,400)
        dados=dados_validos();dados['cnh_categoria']='B'
        self.assertEqual(self.concluir(token,dados).status_code,400)
        result=self.publico.post('/api/operacoes/cadastro-publico/concluir/',{'token':token,'dados':None},format='json')
        self.assertEqual(result.status_code,400)
        self.aluguel.refresh_from_db()
        self.assertIsNone(self.aluguel.cadastro_preenchido_em)

    def test_expira_e_revoga_link_anterior_e_bloqueia_reabertura_apos_assinatura(self):
        antigo=self.gerar();novo=self.gerar()
        self.assertEqual(self.publico.post('/api/operacoes/cadastro-publico/consultar/',{'token':antigo},format='json').status_code,404)
        self.aluguel.refresh_from_db();self.aluguel.cadastro_expira_em=timezone.now()-timedelta(seconds=1);self.aluguel.save()
        self.assertEqual(self.concluir(novo).status_code,410)
        self.aluguel.assinatura_status='pendente';self.aluguel.save()
        self.assertEqual(self.client.post(self.rota+'/cadastro/',{'reabrir':True},format='json').status_code,400)

    def test_reabertura_desabilita_assinatura_e_exige_novo_preenchimento(self):
        token=self.gerar();self.assertEqual(self.concluir(token).status_code,200)
        self.assertEqual(self.client.post(self.rota+'/cadastro/',{},format='json').status_code,400)
        result=self.client.post(self.rota+'/cadastro/',{'reabrir':True},format='json')
        self.assertEqual(result.status_code,201)
        self.aluguel.refresh_from_db();self.assertFalse(cadastro_completo(self.aluguel))
        with patch('core.assinatura.requests.post') as enviar:
            self.assertEqual(self.client.post(self.rota+'/assinatura/',{},format='json').status_code,400)
            enviar.assert_not_called()

    def test_nao_autenticado_nao_gera_link(self):
        self.assertEqual(self.publico.post(self.rota+'/cadastro/',{},format='json').status_code,401)
