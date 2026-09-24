from django.contrib import admin
from django.urls import path

from django_extensions_admin import commands

from .testapp.admin import (
    choices_site,
    guarded_site,
    instant_site,
    readonly_site,
    recent_site,
    restricted_site,
)

urlpatterns = [
    # Before admin.site.urls, which ends with a catch-all.
    path("admin/commands/", commands.urls(admin.site)),
    path("admin/", admin.site.urls),
    path("restricted/", restricted_site.urls),
    path("guarded/", guarded_site.urls),
    path("readonly/", readonly_site.urls),
    path("instant/", instant_site.urls),
    path("recent/", recent_site.urls),
    path("choices/", choices_site.urls),
]
