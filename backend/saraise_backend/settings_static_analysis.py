"""Django settings bootstrap for static analysis only."""

import logging
import os

from django.core.management.utils import get_random_secret_key

os.environ.setdefault("SECRET_KEY", get_random_secret_key())
os.environ.setdefault("ALLOWED_HOSTS", "localhost")

from src.core.observability.logging import JSONFormatter, ObservabilityContextFilter  # noqa: E402

from .settings import *  # noqa: E402,F401,F403

_security_handler = logging.NullHandler()
_security_handler.setFormatter(JSONFormatter())
_security_handler.addFilter(ObservabilityContextFilter())
_security_logger = logging.getLogger("saraise.security_access_control")
_security_logger.handlers = [_security_handler]
_security_logger.propagate = False
