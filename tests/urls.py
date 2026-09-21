from django.contrib import admin
from django.urls import path

from .testapp.admin import guarded_site, instant_site, readonly_site, recent_site, restricted_site

urlpatterns = [
    path("admin/", admin.site.urls),
    path("restricted/", restricted_site.urls),
    path("guarded/", guarded_site.urls),
    path("readonly/", readonly_site.urls),
    path("instant/", instant_site.urls),
    path("recent/", recent_site.urls),
]
