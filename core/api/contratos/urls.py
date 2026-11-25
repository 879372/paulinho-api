from django.urls import path
from .views import ContratoCreateView, ContratoDetailView, comprovante, concluir_contrato, instrumento, editar_contrato, excluir_contrato, quitar_principal

urlpatterns = [
    path('', ContratoCreateView.as_view(), name='contrato-create'),
    path('<int:pk>/', ContratoDetailView.as_view(), name='contrato-detail'),
    path('<int:pk>/comprovante/', comprovante, name='contrato-comprovante'),
    path('<int:pk>/instrumento/', instrumento, name='contrato-instrumento'),
    path('<int:pk>/editar/', editar_contrato, name='contrato-editar'),
    path('<int:pk>/concluir/', concluir_contrato, name='contrato-concluir'),
    path('<int:pk>/excluir/', excluir_contrato, name='contrato-excluir'),
    path('<int:pk>/quitar-principal/', quitar_principal, name='contrato-quitar-principal'),
]
