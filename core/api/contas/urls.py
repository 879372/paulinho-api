from django.urls import path

from .views import ContaPagarDetailView, ContaPagarListCreateView


urlpatterns = [
    path('', ContaPagarListCreateView.as_view(), name='contas-a-pagar'),
    path('<int:pk>/', ContaPagarDetailView.as_view(), name='conta-a-pagar-detail'),
]
