from django.contrib import admin
from django.urls import path, include

from sheets.debug_views import debug_errors

urlpatterns = [
    path("debug/sync-errors/", debug_errors),
    path("admin/", admin.site.urls),
    path("", include("sheets.urls")),
]
