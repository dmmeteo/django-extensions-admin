from django.contrib import admin
from django.urls import path

from .testapp.admin import restricted_site

urlpatterns = [
    path("admin/", admin.site.urls),
    path("restricted/", restricted_site.urls),
]
