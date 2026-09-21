from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),  # login, signup, logout, Google OAuth
    path("", include("tracker.urls")),
]
