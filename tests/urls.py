from django.contrib import admin
from django.urls import path

from .testapp.admin import guarded_site, readonly_site, restricted_site

urlpatterns = [
    path("admin/", admin.site.urls),
    path("restricted/", restricted_site.urls),
    path("guarded/", guarded_site.urls),
    path("readonly/", readonly_site.urls),
]
