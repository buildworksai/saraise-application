"""
Authentication URL routing.
"""

from django.urls import path

from .auth_api import (
    current_user_view,
    login_view,
    logout_view,
    refresh_session_view,
    register_view,
    update_profile_view,
)

urlpatterns = [
    path("login/", login_view, name="login"),
    path("register/", register_view, name="register"),
    path("logout/", logout_view, name="logout"),
    path("me/", current_user_view, name="current_user"),
    path("profile/", update_profile_view, name="update_profile"),
    path("refresh/", refresh_session_view, name="refresh_session"),
]
