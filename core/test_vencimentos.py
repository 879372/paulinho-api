from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from core.models import Cliente, Contrato, Parcela
from core.api.contratos.services import adicionar_periodo
from operacoes.models import Moto, Aluguel, CobrancaAluguel, Movimento


class VencimentoIndividualTests(TestCase):
    def setUp(self):
        self.client=APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user('vencimento'))
        self.hoje=timezone.localdate()
        self.cliente=Cliente.objects.create(nome='Cliente',telefone='84999990000')
        self.contrato=Contrato.objects.create(cliente=self.cliente,tipo='emprestimo_tradicional',data_inicio=self.hoje-timedelta(days=30),data_primeira_parcela=self.hoje,valor_principal=400,valor_parcela=200,qtd_parcelas=2,periodicidade='mensal',dia_vencimento=10)
        self.atual=Parcela.objects.create(contrato=self.contrato,numero=1,valor=200,data_vencimento=self.hoje)
        self.proxima=Parcela.objects.create(contrato=self.contrato,numero=2,valor=200,data_vencimento=adicionar_periodo(self.hoje,1,'mensal'))
        self.url=f'/api/parcelas/{self.atual.pk}/vencimento/'

    def test_altera_apenas_parcela_preserva_contrato_valores_e_data_original(self):
        novo=self.hoje+timedelta(days=7)
        response=self.client.patch(self.url,{'vencimento':str(novo),'vencimento_atual':str(self.hoje)})
        self.assertEqual(response.status_code,200,response.data)
        self.atual.refresh_from_db();self.proxima.refresh_from_db();self.contrato.refresh_from_db()
        self.assertEqual(self.atual.data_vencimento,novo)
        self.assertEqual(self.atual.data_vencimento_original,self.hoje)
        self.assertEqual(self.atual.valor,Decimal('200'))
        self.assertEqual(self.proxima.data_vencimento,adicionar_periodo(self.hoje,1,'mensal'))
        self.assertEqual((self.contrato.data_primeira_parcela,self.contrato.dia_vencimento,self.contrato.periodicidade,self.contrato.qtd_parcelas),(self.hoje,10,'mensal',2))
        self.assertEqual(self.client.patch(self.url,{'vencimento':str(novo+timedelta(days=1)),'vencimento_atual':str(novo)}).status_code,200)
        self.atual.refresh_from_db()
        self.assertEqual(self.atual.data_vencimento_original,self.hoje)
        self.assertEqual(Movimento.objects.count(),0)

    def test_rejeita_data_invalida_conflito_pago_e_sem_login(self):
        self.assertEqual(self.client.patch(self.url,{'vencimento':'invalida','vencimento_atual':str(self.hoje)}).status_code,400)
        self.assertEqual(self.client.patch(self.url,{'vencimento':str(self.hoje+timedelta(days=1)),'vencimento_atual':str(self.hoje-timedelta(days=1))}).status_code,409)
        self.atual.status='paga';self.atual.save()
        self.assertEqual(self.client.get(self.url).status_code,400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code,401)

    def test_juros_mantem_ciclo_original_apos_baixa_da_cobranca_prorrogada(self):
        self.proxima.delete()
        self.contrato.tipo='emprestimo_somente_juros';self.contrato.valor_juros_mensal=200;self.contrato.save()
        self.atual.tipo='juros_mensal';self.atual.numero=None;self.atual.save()
        planejado=adicionar_periodo(self.hoje,1,'mensal')
        self.assertEqual(self.client.patch(self.url,{'vencimento':str(planejado),'vencimento_atual':str(self.hoje)}).status_code,200)
        baixa=self.client.patch(f'/api/parcelas/{self.atual.pk}/dar-baixa/',{'data_pagamento':str(self.hoje),'forma_pagamento':'pix','valor_pago':'200'})
        self.assertEqual(baixa.status_code,200,baixa.data)
        seguinte=self.contrato.parcelas.exclude(pk=self.atual.pk).get()
        self.assertEqual(seguinte.data_vencimento,planejado)
        self.assertEqual(seguinte.status,'pendente')
        self.assertEqual(seguinte.valor,Decimal('200'))

    def test_aluguel_edita_uma_cobranca_sem_alterar_periodo_e_rejeita_colisao(self):
        moto=Moto.objects.create(placa='ABC1D23',modelo='CG')
        aluguel=Aluguel.objects.create(cliente=self.cliente,moto=moto,inicio=self.hoje,fim=self.hoje+timedelta(days=14),primeiro_vencimento=self.hoje,valor=100,periodicidade='semanal')
        atual=CobrancaAluguel.objects.create(aluguel=aluguel,vencimento=self.hoje,valor=100)
        futura=CobrancaAluguel.objects.create(aluguel=aluguel,vencimento=self.hoje+timedelta(days=7),valor=100)
        url=f'/api/operacoes/alugueis/cobrancas/{atual.pk}/vencimento/'
        self.assertEqual(self.client.patch(url,{'vencimento':str(futura.vencimento),'vencimento_atual':str(self.hoje)}).status_code,400)
        novo=self.hoje+timedelta(days=2)
        self.assertEqual(self.client.patch(url,{'vencimento':str(novo),'vencimento_atual':str(self.hoje)}).status_code,200)
        atual.refresh_from_db();futura.refresh_from_db();aluguel.refresh_from_db()
        self.assertEqual(atual.vencimento,novo)
        self.assertEqual(atual.vencimento_original,self.hoje)
        self.assertEqual(futura.vencimento,self.hoje+timedelta(days=7))
        self.assertEqual(aluguel.primeiro_vencimento,self.hoje)
        self.assertEqual(aluguel.fim,self.hoje+timedelta(days=14))
