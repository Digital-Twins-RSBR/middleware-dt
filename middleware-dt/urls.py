# thingsboard_middleware/urls.py
from django.contrib import admin
from django.urls import path, include
from facade.api import router as facade_router
from orchestrator.api import router as orchestrator_router
from ninja import NinjaAPI

api = NinjaAPI()

# Adicione as rotas dos apps 'orchestrator' e 'facade' à instância principal
api.add_router("/orchestrator", orchestrator_router)
api.add_router("/facade", facade_router)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),
    # path('api/orchestrator/', orchestrator_api.urls),  # Registrar as URLs do orchestrator_api
    # path('api/facade/', facade_api.urls),  
]
