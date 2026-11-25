from django.urls import path
from .views import CobrancasDoDiaListView, dashboard_view

urlpatterns = [
    path('cobrancas-do-dia/', CobrancasDoDiaListView.as_view(), name='cobrancas-do-dia'),
    path('dashboard/', dashboard_view, name='dashboard'),
]
