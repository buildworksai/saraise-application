"""Deprecated v1 compatibility routes.

Only the legacy company resource remains on v1. New financial capabilities and
readiness reporting are deliberately available only through governed v2.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import CompanyViewSet

app_name = "multi_company_v1"
router = DefaultRouter()
router.register("companies", CompanyViewSet, basename="company")

urlpatterns = [path("", include(router.urls))]
