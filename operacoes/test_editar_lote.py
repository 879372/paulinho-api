from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from .models import LoteAnimal, Movimento

class EditarLoteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user('edicao-lote'))
        self.hoje = timezone.localdate()
        r = self.client.post('/api/operacoes/animais/', {'identificacao':'Lote A', 'especie':'Caprinos', 'quantidade':3, 'data_aquisicao':str(self.hoje), 'valor_compra':'900.00'}, format='json')
        self.assertEqual(r.status_code,201,r.data)
        self.lote = LoteAnimal.objects.get(pk=r.data['id'])
        self.url = f'/api/operacoes/animais/{self.lote.pk}/'

    def test_edita_compra_sem_duplicar_despesa_e_preserva_outros_movimentos(self):
        compra = Movimento.objects.get(lote=self.lote)
        despesa = Movimento.objects.create(lote=self.lote,descricao='Ração',categoria='alimentacao',tipo='saida',valor=50,data=self.hoje)
        nova_data = self.hoje-timedelta(days=1)
        r=self.client.patch(self.url,{'identificacao':'Lote B','especie':'Ovinos','quantidade':4,'valor_compra':'1000.00','data_aquisicao':str(nova_data),'observacoes':'Corrigido','encerrado':True},format='json')
        self.assertEqual(r.status_code,200,r.data)
        self.lote.refresh_from_db();compra.refresh_from_db();despesa.refresh_from_db()
        self.assertEqual(self.lote.quantidade,4)
        self.assertTrue(self.lote.encerrado)
        self.assertEqual(compra.valor,1000)
        self.assertEqual(compra.data,nova_data)
        self.assertEqual(compra.descricao,'Compra: Lote B')
        self.assertEqual(despesa.valor,50)
        self.assertEqual(Movimento.objects.filter(lote=self.lote).count(),2)
        caixa=self.client.get('/api/operacoes/financeiro/',{'inicio':str(nova_data),'fim':str(self.hoje)}).data
        self.assertEqual(caixa['saidas'],1050)
        self.assertEqual(self.client.get(self.url).status_code,200)

    def test_rejeita_invalido_e_exige_login(self):
        for dados in ({'quantidade':0},{'data_aquisicao':str(self.hoje+timedelta(days=1))},{'valor_compra':'-1'}):
            self.assertEqual(self.client.patch(self.url,dados,format='json').status_code,400)
        self.lote.refresh_from_db();self.assertEqual(self.lote.valor_compra,900)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.patch(self.url,{'quantidade':4},format='json').status_code,401)

    def test_valor_zero_e_novo_valor_reutilizam_mesmo_lancamento(self):
        pk=Movimento.objects.get(lote=self.lote).pk
        for valor in ('0.00','500.00'):
            r=self.client.patch(self.url,{'valor_compra':valor},format='json')
            self.assertEqual(r.status_code,200,r.data)
            self.assertEqual(Movimento.objects.get(lote=self.lote).pk,pk)
