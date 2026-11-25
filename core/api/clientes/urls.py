from django.urls import path
from .views import ClienteDetailView, ClienteListCreateView, relatorio

urlpatterns = [
    path('', ClienteListCreateView.as_view(), name='cliente-list'),
    path('<int:pk>/', ClienteDetailView.as_view(), name='cliente-detail'),
    path('<int:pk>/relatorio/', relatorio, name='cliente-relatorio'),
]
