"""Bounded page-number pagination and its governed OpenAPI envelope."""

from __future__ import annotations

from typing import Mapping, Sequence

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

_PAGINATION_MARKER = "_saraise_v2_pagination"


class GovernedPageNumberPagination(PageNumberPagination):
    """API v2 paginator with a fixed safe default and hard upper bound."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data: Sequence[object]) -> Response:
        """Return page data and attach protocol metadata for the renderer."""

        page = getattr(self, "page", None)
        if page is None:
            raise RuntimeError("paginate_queryset() must be called before get_paginated_response()")

        count = page.paginator.count
        pagination = {
            "count": count,
            "page": page.number,
            "page_size": page.paginator.per_page,
            "total_pages": page.paginator.num_pages if count else 0,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
        }
        response = Response(data)
        setattr(response, _PAGINATION_MARKER, pagination)
        return response

    def get_paginated_response_schema(self, schema: Mapping[str, object]) -> dict[str, object]:
        """Describe the actual post-render v2 collection response."""

        return {
            "type": "object",
            "required": ["data", "meta"],
            "properties": {
                "data": {"type": "array", "items": dict(schema)},
                "meta": {
                    "type": "object",
                    "required": ["correlation_id", "timestamp", "pagination"],
                    "properties": {
                        "correlation_id": {"type": "string"},
                        "timestamp": {"type": "string", "format": "date-time"},
                        "pagination": {
                            "type": "object",
                            "required": [
                                "count",
                                "page",
                                "page_size",
                                "total_pages",
                                "has_next",
                                "has_previous",
                            ],
                            "properties": {
                                "count": {"type": "integer", "minimum": 0},
                                "page": {"type": "integer", "minimum": 1},
                                "page_size": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": self.max_page_size,
                                    "default": self.page_size,
                                },
                                "total_pages": {"type": "integer", "minimum": 0},
                                "has_next": {"type": "boolean"},
                                "has_previous": {"type": "boolean"},
                            },
                        },
                    },
                },
            },
        }


GovernedPagination = GovernedPageNumberPagination
SaraiseV2Pagination = GovernedPageNumberPagination
