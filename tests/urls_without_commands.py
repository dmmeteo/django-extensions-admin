"""The stock admin alone: the app is installed, but the command pages are not included."""

from django.contrib import admin
from django.urls import path

urlpatterns = [path("admin/", admin.site.urls)]
