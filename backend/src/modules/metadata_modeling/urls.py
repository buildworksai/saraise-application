from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import EntityDefinitionViewSet, DynamicResourceViewSet

router = DefaultRouter()
router.register(r"entity-definitions", EntityDefinitionViewSet, basename="entity-definition")
router.register(r"resources", DynamicResourceViewSet, basename="dynamic-resource")

urlpatterns = [
    path("", include(router.urls)),
]
