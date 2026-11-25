from datetime import timedelta
from io import StringIO
from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from core.models import Cliente, Contrato, Parcela, ContaPagar, LembreteDiario
from operacoes.models import Moto, Aluguel, CobrancaAluguel


@override_settings(EVOLUTION_API_URL='https://evolution.test', EVOLUTION_API_KEY='teste', EVOLUTION_INSTANCE='paulinho', OWNER_WHATSAPP='5584999990000', LEMBRETES_INTERVALO=0)
class LembretesDiariosTests(TestCase):
    def setUp(self):
        self.hoje = timezone.localdate()
        self.cliente = Cliente.objects.create(nome='Cliente', telefone='84999990001')
        self.contrato = Contrato.objects.create(cliente=self.cliente, tipo='emprestimo_tradicional', data_inicio=self.hoje, valor_principal=100)
        for indice, dias in enumerate([-1, 0, 1], 1):
            Parcela.objects.create(contrato=self.contrato, numero=indice, data_vencimento=self.hoje+timedelta(days=dias), valor=50)
        moto = Moto.objects.create(placa='ABC1D23', modelo='CG')
        aluguel = Aluguel.objects.create(cliente=self.cliente, moto=moto, inicio=self.hoje-timedelta(days=7), fim=self.hoje+timedelta(days=14), primeiro_vencimento=self.hoje, valor=100, periodicidade='semanal')
        for dias in [-1, 0, 1]:
            CobrancaAluguel.objects.create(aluguel=aluguel, vencimento=self.hoje+timedelta(days=dias), valor=100)
        ContaPagar.objects.create(descricao='Energia', dia_vencimento=self.hoje.day)

    @patch('core.management.commands.enviar_lembretes_diarios.verificar_conexao')
    @patch('core.management.commands.enviar_lembretes_diarios.enviar_whatsapp')
    def test_envia_hoje_atrasos_e_resumo_sem_duplicar(self, enviar, verificar):
        call_command('enviar_lembretes_diarios', stdout=StringIO())
        self.assertEqual(enviar.call_count, 5)
        resumo = enviar.call_args_list[0].args[1]
        self.assertIn('Energia', resumo)
        self.assertIn('ALUGUÉIS DE MOTOS', resumo)
        self.assertTrue(any('vence hoje' in c.args[1] for c in enviar.call_args_list))
        self.assertEqual(LembreteDiario.objects.filter(status='enviado').count(), 5)
        call_command('enviar_lembretes_diarios', stdout=StringIO())
        self.assertEqual(enviar.call_count, 5)

    @patch('core.management.commands.enviar_lembretes_diarios.verificar_conexao')
    @patch('core.management.commands.enviar_lembretes_diarios.enviar_whatsapp')
    def test_dry_run_e_pagamentos_nao_enviam(self, enviar, verificar):
        call_command('enviar_lembretes_diarios', dry_run=True, stdout=StringIO())
        enviar.assert_not_called()
        self.assertEqual(LembreteDiario.objects.count(), 0)
        Parcela.objects.update(status='paga')
        CobrancaAluguel.objects.update(pago_em=self.hoje)
        call_command('enviar_lembretes_diarios', stdout=StringIO())
        self.assertEqual(enviar.call_count, 1)

    @patch('core.management.commands.enviar_lembretes_diarios.verificar_conexao')
    @patch('core.management.commands.enviar_lembretes_diarios.enviar_whatsapp')
    def test_falha_isolada_nao_interrompe_demais_nem_repete(self, enviar, verificar):
        enviar.side_effect = [None, RuntimeError('falha'), None, None, None]
        with self.assertRaises(CommandError):
            call_command('enviar_lembretes_diarios', stdout=StringIO(), stderr=StringIO())
        self.assertEqual(LembreteDiario.objects.filter(status='falha').count(), 1)
        self.assertEqual(LembreteDiario.objects.filter(status='enviado').count(), 4)
        call_command('enviar_lembretes_diarios', stdout=StringIO())
        self.assertEqual(enviar.call_count, 5)

    @patch('core.management.commands.enviar_lembretes_diarios.requests.get')
    @patch('core.management.commands.enviar_lembretes_diarios.enviar_whatsapp')
    def test_desconectada_falha_sem_registrar_envios(self, enviar, consultar):
        consultar.return_value = Mock(json=lambda: {'instance': {'state': 'close'}})
        with self.assertRaises(CommandError):
            call_command('enviar_lembretes_diarios', stdout=StringIO())
        enviar.assert_not_called()
        self.assertEqual(LembreteDiario.objects.count(), 0)
