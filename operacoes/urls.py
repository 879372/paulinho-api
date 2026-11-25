from django.urls import path
from . import views

urlpatterns = [
    path('motos/', views.MotosView.as_view()),
    path('alugueis/', views.AlugueisView.as_view()),
    path('alugueis/<int:pk>/contrato/', views.contrato_aluguel),
    path('alugueis/cobrancas/<int:pk>/receber/', views.receber_aluguel),
    path('animais/', views.LotesView.as_view()),
    path('movimentos/', views.MovimentosView.as_view()),
    path('financeiro/', views.financeiro),
]
