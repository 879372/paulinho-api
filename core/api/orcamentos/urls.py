from django.urls import path

from .views import gerar_orcamento


urlpatterns = [path('gerar/', gerar_orcamento, name='gerar-orcamento')]
