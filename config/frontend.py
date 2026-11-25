from django.conf import settings
from django.http import FileResponse, Http404
from django.views.decorators.http import require_safe


@require_safe
def frontend(request):
    index = settings.FRONTEND_DIST / 'index.html'
    if not settings.SERVE_FRONTEND or not index.is_file():
        raise Http404
    response = FileResponse(index.open('rb'), content_type='text/html; charset=utf-8')
    response['Cache-Control'] = 'no-store'
    return response
