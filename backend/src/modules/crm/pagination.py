"""
Pagination classes for CRM module.

Per plan requirement: default 20, max 100.
"""

from rest_framework.pagination import PageNumberPagination


class CRMResultsSetPagination(PageNumberPagination):
    """Pagination for CRM module endpoints.
    
    Default page size: 20
    Max page size: 100
    Page size query parameter: page_size
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
