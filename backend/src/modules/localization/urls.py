"""
URL routing for Localization module.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api import (
    CurrencyConfigViewSet,
    LanguageViewSet,
    LocaleConfigViewSet,
    RegionalSettingsViewSet,
    TranslationViewSet,
)
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"languages", LanguageViewSet, basename="language")
router.register(r"translations", TranslationViewSet, basename="translation")
router.register(r"locale-configs", LocaleConfigViewSet, basename="locale-config")
router.register(r"currency-configs", CurrencyConfigViewSet, basename="currency-config")
router.register(r"regional-settings", RegionalSettingsViewSet, basename="regional-settings")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
