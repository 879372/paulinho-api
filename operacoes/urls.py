from django.urls import path
from core.vencimentos import vencimento_aluguel
from core.adiamento import adiar_aluguel
from . import views
from .cadastro import gerenciar_cadastro, consultar_publico, concluir_publico

urlpatterns = [
    path('cadastro-publico/consultar/', consultar_publico),
    path('cadastro-publico/concluir/', concluir_publico),
    path('alugueis/<int:pk>/cadastro/', gerenciar_cadastro),
    path('alugueis/cobrancas/<int:pk>/vencimento/', vencimento_aluguel),
    path('alugueis/cobrancas/<int:pk>/adiar/', adiar_aluguel),
    path('motos/', views.MotosView.as_view()),
    path('alugueis/cobrancas/', views.CobrancasAluguelView.as_view()),
    path('alugueis/', views.AlugueisView.as_view()),
    path('alugueis/<int:pk>/caucao/receber/', views.movimentar_caucao, {'acao': 'receber'}),
    path('alugueis/<int:pk>/caucao/devolver/', views.movimentar_caucao, {'acao': 'devolver'}),
    path('alugueis/<int:pk>/caucao/', views.atualizar_caucao),
    path('alugueis/<int:pk>/contrato/', views.contrato_aluguel),
    path('alugueis/<int:pk>/assinatura/', views.assinatura_aluguel),
    path('alugueis/<int:pk>/assinatura/pdf/', views.assinatura_aluguel_pdf),
    path('alugueis/cobrancas/<int:pk>/receber/', views.receber_aluguel),
    path('animais/', views.LotesView.as_view()),
    path('movimentos/', views.MovimentosView.as_view()),
    path('financeiro/', views.financeiro),
]
