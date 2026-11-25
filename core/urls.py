from django.urls import include, path

# A raiz só compõe os módulos. Cada domínio controla suas próprias rotas.
urlpatterns = [
    path('clientes/', include('core.api.clientes.urls')),
    path('contratos/', include('core.api.contratos.urls')),
    path('parcelas/', include('core.api.parcelas.urls')),
    path('contas-a-pagar/', include('core.api.contas.urls')),
    path('comprovantes/', include('core.api.comprovantes.urls')),
    path('orcamentos/', include('core.api.orcamentos.urls')),
    path('', include('core.api.cobrancas.urls')),
]
