from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from django.views.generic import RedirectView

urlpatterns = [
    path('', RedirectView.as_view(url='/admin/', permanent=False)),
    path('admin/', admin.site.urls),

    # Rutas de la app de usuarios
    path('api/accounts/', include('accounts.urls')),
    # Rutas de la app de estudio
    path('api/studio/', include('studio.urls')),
    

    # Endpoints para autenticación JWT
    path('api/auth/', include('accounts.urls')),
]
