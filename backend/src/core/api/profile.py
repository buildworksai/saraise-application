"""Opt-in API v2 settings and view mixins.

Nothing in this module mutates Django's global ``REST_FRAMEWORK`` setting.
Existing API v1 views therefore retain their raw JSON renderer and behavior.
"""

from __future__ import annotations

from collections.abc import Callable

from rest_framework.parsers import BaseParser, FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .envelope import SuccessEnvelopeRenderer
from .exception_handler import stable_exception_handler
from .pagination import GovernedPageNumberPagination

API_V2_SETTINGS_PROFILE: dict[str, object] = {
    "DEFAULT_RENDERER_CLASSES": ["src.core.api.envelope.SuccessEnvelopeRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "src.core.api.pagination.GovernedPageNumberPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "src.core.api.exception_handler.stable_exception_handler",
}


class GovernedAPIViewMixin:
    """Scope the governed renderer, exceptions and pagination to API v2."""

    renderer_classes = (SuccessEnvelopeRenderer,)
    parser_classes: tuple[type[BaseParser], ...] = (JSONParser,)
    pagination_class = GovernedPageNumberPagination

    def get_exception_handler(self) -> Callable[[Exception, dict[str, object]], Response]:
        """Use the stable v2 exception handler without changing v1 settings."""

        return stable_exception_handler


class GovernedMultipartAPIViewMixin(GovernedAPIViewMixin):
    """Opt in upload actions to multipart/form parsing while retaining JSON."""

    parser_classes: tuple[type[BaseParser], ...] = (JSONParser, MultiPartParser, FormParser)
