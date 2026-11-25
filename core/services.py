"""Compatibilidade temporária: serviços migraram para os módulos de domínio."""
from core.api.cobrancas.services import atualizar_atrasos, cobrancas_do_dia, gerar_juros_mensais
from core.api.contratos.services import adicionar_meses as add_months
from core.api.contratos.services import gerar_parcelas_do_contrato as gerar_parcelas
from core.api.contratos.services import monetario as money

__all__ = ['add_months', 'atualizar_atrasos', 'cobrancas_do_dia', 'gerar_juros_mensais', 'gerar_parcelas', 'money']
