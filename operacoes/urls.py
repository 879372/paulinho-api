from django.urls import path
from core.adiamento import adiar_aluguel
from . import views

urlpatterns = [
    path('alugueis/cobrancas/<int:pk>/adiar/', adiar_aluguel),
    path('motos/', views.MotosView.as_view()),
    path('alugueis/cobrancas/', views.CobrancasAluguelView.as_view()),
    path('alugueis/', views.AlugueisView.as_view()),
    path('alugueis/<int:pk>/contrato/', views.contrato_aluguel),
    path('alugueis/<int:pk>/assinatura/', views.assinatura_aluguel),
    path('alugueis/<int:pk>/assinatura/pdf/', views.assinatura_aluguel_pdf),
    path('alugueis/cobrancas/<int:pk>/receber/', views.receber_aluguel),
    path('animais/', views.LotesView.as_view()),
    path('movimentos/', views.MovimentosView.as_view()),
    path('financeiro/', views.financeiro),
]
