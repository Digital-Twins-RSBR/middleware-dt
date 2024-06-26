# thingsboard_middleware/urls.py
from django.contrib import admin
from django.urls import path, include
from facade.api import app


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', app.urls),
]
