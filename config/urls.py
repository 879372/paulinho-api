from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path, re_path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from core.views import LoginThrottle
from .frontend import frontend

class LoginView(TokenObtainPairView):
    throttle_classes = [LoginThrottle]

def healthcheck(request):
    return JsonResponse({'status': 'ok'})


urlpatterns = [path('api/operacoes/', include('operacoes.urls')), path('api/health/', healthcheck, name='healthcheck'), path('admin/', admin.site.urls), path('api/auth/login/', LoginView.as_view()),
               path('api/auth/refresh/', TokenRefreshView.as_view()), path('api/', include('core.urls'))]

urlpatterns += [re_path(r'^(?!(?:api|admin|static|assets)(?:/|$)).*$', frontend)]
