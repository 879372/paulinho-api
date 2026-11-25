"""Compatibilidade temporária. Importe dos módulos em core.api.*."""
from core.api.clientes.serializers import ClienteSerializer
from core.api.contratos.serializers import ContratoCreateSerializer, ContratoDetailSerializer
from core.api.parcelas.serializers import BaixaParcelaSerializer, ParcelaSerializer

ContratoSerializer = ContratoDetailSerializer
BaixaSerializer = BaixaParcelaSerializer
