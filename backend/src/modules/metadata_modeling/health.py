"""Compatibility export for the governed, tenant-safe module health view."""

from .api import MetadataHealthView

health_check = MetadataHealthView.as_view()

__all__ = ["health_check"]
