"""
Pagination classes for CRM module.

Limits are resolved from tenant configuration for each request.
"""

from src.core.api import GovernedPageNumberPagination

from .configuration import DEFAULT_CRM_CONFIGURATION, effective_configuration


class CRMResultsSetPagination(GovernedPageNumberPagination):
    """Pagination for CRM module endpoints.

    The query parameter and safe bound are governed by tenant configuration.
    """

    page_size_query_param = "page_size"

    def get_page_size(self, request):
        tenant_id = getattr(request, "tenant_id", None)
        configuration = (
            effective_configuration(tenant_id)["pagination"]
            if tenant_id is not None
            else DEFAULT_CRM_CONFIGURATION["pagination"]
        )
        self.page_size = int(configuration["default_page_size"])
        self.max_page_size = int(configuration["maximum_page_size"])
        return super().get_page_size(request)
