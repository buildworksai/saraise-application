"""
Authentication URL routing.
"""
from django.urls import path
from .auth_api import (
    login_view, 
    logout_view, 
    current_user_view, 
    refresh_session_view,
    register_view,
)

urlpatterns = [
    path('login/', login_view, name='login'),
    path('register/', register_view, name='register'),
    path('logout/', logout_view, name='logout'),
    path('me/', current_user_view, name='current_user'),
    path('refresh/', refresh_session_view, name='refresh_session'),
]

