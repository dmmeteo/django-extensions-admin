from django.contrib import admin
from django.urls import path

from django_extensions_admin import commands

urlpatterns = [
    # Before admin.site.urls, which ends with a catch-all.
    path("admin/commands/", commands.urls(admin.site)),
    path("admin/", admin.site.urls),
]
