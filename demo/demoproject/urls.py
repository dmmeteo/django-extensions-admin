from django.contrib import admin
from django.urls import include, path

from django_extensions_admin import commands

urlpatterns = [
    # Before admin.site.urls, which ends with a catch-all.
    path("admin/commands/", commands.urls(admin.site)),
    path("admin/repl/", include("django_extensions_admin.repl.urls")),
    path("admin/", admin.site.urls),
]
