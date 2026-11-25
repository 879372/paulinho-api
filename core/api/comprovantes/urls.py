from django.urls import path

from .views import gerar_comprovante


urlpatterns = [path('gerar/', gerar_comprovante, name='gerar-comprovante-compra')]
