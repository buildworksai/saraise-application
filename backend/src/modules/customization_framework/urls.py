"""API v2 routes for customization framework; no active legacy surface."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    BusinessRuleVersionViewSet,
    BusinessRuleViewSet,
    FieldDefinitionViewSet,
    FieldValueViewSet,
    FormDefinitionViewSet,
    FormLayoutVersionViewSet,
    ModuleHealthAPIView,
    ResourceContractViewSet,
    RuleExecutionViewSet,
    RuntimeConfigurationViewSet,
)

app_name = "customization_framework"
router = DefaultRouter()
router.register("resource-contracts", ResourceContractViewSet, basename="resource-contract")
router.register("field-definitions", FieldDefinitionViewSet, basename="field-definition")
router.register("field-values", FieldValueViewSet, basename="field-value")
router.register("forms", FormDefinitionViewSet, basename="form")
router.register("form-layouts", FormLayoutVersionViewSet, basename="form-layout")
router.register("rules", BusinessRuleViewSet, basename="rule")
router.register("rule-versions", BusinessRuleVersionViewSet, basename="rule-version")
router.register("rule-executions", RuleExecutionViewSet, basename="rule-execution")
router.register("configuration", RuntimeConfigurationViewSet, basename="configuration")

urlpatterns = [path("", include(router.urls)), path("health/", ModuleHealthAPIView.as_view(), name="health")]
