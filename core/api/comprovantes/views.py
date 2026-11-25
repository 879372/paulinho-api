from rest_framework.decorators import api_view

from .pdf import comprovante_compra_pdf
from .serializers import ComprovanteCompraSerializer


@api_view(['POST'])
def gerar_comprovante(request):
    serializer = ComprovanteCompraSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return comprovante_compra_pdf(serializer.validated_data)
