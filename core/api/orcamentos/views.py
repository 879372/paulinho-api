from rest_framework.decorators import api_view

from .pdf import orcamento_pdf
from .serializers import OrcamentoSerializer


@api_view(['POST'])
def gerar_orcamento(request):
    serializer = OrcamentoSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return orcamento_pdf(serializer.validated_data)
