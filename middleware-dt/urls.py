# thingsboard_middleware/urls.py
from django.contrib import admin
from django.conf import settings
from django.urls import path, include
from core.api import router as core_router
from core.views import index 
from facade.api import router as facade_router
from orchestrator.api import router as orchestrator_router
from ninja import NinjaAPI, Redoc
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.views.generic.base import RedirectView

import os

# api = NinjaAPI(docs=Redoc())
# Expor esquema de segurança OpenAPI para permitir 'Authorize' (Bearer JWT)
api = NinjaAPI(openapi_extra={
    "components": {
        "securitySchemes": {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT"
            }
        }
    }
})

# Adicione as rotas dos apps 'orchestrator' e 'facade' à instância principal
api.add_router("/core", core_router)
api.add_router("/orchestrator", orchestrator_router)
api.add_router("/facade", facade_router)

urlpatterns = []
for app in settings.INSTALLED_APPS:
    if not app.startswith('django.'):
        if os.path.exists(os.path.join(settings.BASE_DIR, f'{app}/urls.py')):
            urlpatterns += [path(f'{app}/' , include(f'{app}.urls'))]

urlpatterns += [
    path('', index, name='index'),
    path('admin/', admin.site.urls),
    path('api/', api.urls),
    # Support clients requesting the YAML form by redirecting to JSON
    path('api/openapi.yaml', RedirectView.as_view(url='/api/openapi.json', permanent=False)),
]
urlpatterns += staticfiles_urlpatterns()
