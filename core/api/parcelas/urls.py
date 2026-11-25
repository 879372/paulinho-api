from django.urls import path
from .views import ParcelaListView, dar_baixa, desfazer_baixa

urlpatterns = [
    path('', ParcelaListView.as_view(), name='parcela-list'),
    path('<int:pk>/dar-baixa/', dar_baixa, name='parcela-dar-baixa'),
    path('<int:pk>/desfazer-baixa/', desfazer_baixa, name='parcela-desfazer-baixa'),
]
