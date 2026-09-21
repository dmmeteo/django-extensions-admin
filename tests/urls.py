from django.contrib import admin
from django.urls import path

from .testapp.admin import guarded_site, restricted_site

urlpatterns = [
    path("admin/", admin.site.urls),
    path("restricted/", restricted_site.urls),
    path("guarded/", guarded_site.urls),
]
