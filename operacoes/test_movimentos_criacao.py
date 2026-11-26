from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from .models import LoteAnimal, Movimento, Moto

class MovimentoCriacaoTests(TestCase):
    def setUp(self):
        self.api=APIClient();self.api.force_authenticate(get_user_model().objects.create_user('movimentos'))
        self.hoje=timezone.localdate()
        self.lote=LoteAnimal.objects.create(identificacao='Lote',especie='Bovinos',quantidade=2,data_aquisicao=self.hoje,valor_compra=500)
        self.compra=self.mov('compra_animais','saida',500)
    def mov(self,categoria,tipo,valor):
        return Movimento.objects.create(lote=self.lote,categoria=categoria,tipo=tipo,valor=valor,data=self.hoje,descricao='Exemplo')
    def url(self,m): return f'/api/operacoes/animais/movimentos/{m.pk}/'
    def test_edita_e_apaga_receita_despesa_com_reflexo_no_caixa(self):
        for categoria,tipo in [('venda_animais','entrada'),('alimentacao','saida')]:
            m=self.mov(categoria,tipo,100)
            r=self.api.patch(self.url(m),{'valor':'150.00','descricao':'Corrigido'},format='json');self.assertEqual(r.status_code,200,r.data)
            m.refresh_from_db();self.assertEqual(m.valor,150)
            self.assertEqual(self.api.delete(self.url(m)).status_code,204)
            self.assertFalse(Movimento.objects.filter(pk=m.pk).exists())
        self.assertEqual(self.api.get('/api/operacoes/financeiro/').data['saidas'],500)
    def test_compra_sincroniza_lote_e_exclusao_zera_valor(self):
        data=self.hoje-timedelta(days=1)
        r=self.api.patch(self.url(self.compra),{'valor':'700.00','data':str(data)},format='json');self.assertEqual(r.status_code,200,r.data)
        self.lote.refresh_from_db();self.assertEqual(self.lote.valor_compra,700);self.assertEqual(self.lote.data_aquisicao,data)
        self.assertEqual(self.api.delete(self.url(self.compra)).status_code,204)
        self.lote.refresh_from_db();self.assertEqual(self.lote.valor_compra,0)
        self.assertEqual(self.api.get('/api/operacoes/financeiro/').data['saidas'],0)
    def test_rejeita_datas_categorias_troca_de_lote_e_sem_login(self):
        m=self.mov('alimentacao','saida',50)
        for payload in [{'data':str(self.hoje+timedelta(days=1))},{'categoria':'venda_animais'},{'lote':self.lote.pk},{'valor':'-1'}]:
            self.assertEqual(self.api.patch(self.url(m),payload,format='json').status_code,400)
        self.api.force_authenticate(None)
        self.assertEqual(self.api.delete(self.url(m)).status_code,401)
    def test_nao_altera_movimentos_de_moto(self):
        m=Movimento.objects.create(moto=Moto.objects.create(placa='ABC1D23',modelo='CG'),categoria='manutencao',tipo='saida',valor=100,data=self.hoje,descricao='Moto')
        self.assertEqual(self.api.delete(self.url(m)).status_code,404)
    def test_financeiro_edita_e_apaga_manual(self):
        m=Movimento.objects.create(categoria='emprestimos',tipo='entrada',valor=100,data=self.hoje,descricao='Manual')
        url=f'/api/operacoes/movimentos/{m.pk}/'
        r=self.api.patch(url,{'valor':'150.00','categoria':'outros'},format='json');self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(self.api.delete(url).status_code,204)
    def test_financeiro_protege_caucao(self):
        from .models import Aluguel
        moto=Moto.objects.create(placa='DEF2E34',modelo='CG')
        from core.models import Cliente
        m=Movimento.objects.create(moto=moto,categoria='motos',tipo='entrada',valor=100,data=self.hoje,descricao='Caução')
        Aluguel.objects.create(moto=moto,cliente=Cliente.objects.create(nome='Cliente'),inicio=self.hoje,fim=self.hoje+timedelta(days=30),primeiro_vencimento=self.hoje,periodicidade='mensal',valor=250,caucao_recebimento=m)
        url=f'/api/operacoes/movimentos/{m.pk}/'
        self.assertEqual(self.api.patch(url,{'valor':'1.00'},format='json').status_code,400)
        self.assertEqual(self.api.delete(url).status_code,400)
        self.assertFalse(self.api.get('/api/operacoes/movimentos/').data['results'][0]['editavel'])
