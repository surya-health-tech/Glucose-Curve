
from django.contrib import admin
from django.urls import path, include
from core.views import home   # <-- add this
from core.views_dashboard import dashboard 


urlpatterns = [
    path("", home, name="home"),          # <-- add this (root)
    path("api/", include("core.urls")),
    path("admin/", admin.site.urls),
    path("dashboard/", dashboard, name="dashboard"), 
]