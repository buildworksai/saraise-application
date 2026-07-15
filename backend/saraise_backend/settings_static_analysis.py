"""Django settings bootstrap for static analysis only."""

import os

from django.core.management.utils import get_random_secret_key

os.environ.setdefault("SECRET_KEY", get_random_secret_key())
os.environ.setdefault("ALLOWED_HOSTS", "localhost")

from .settings import *  # noqa: E402,F401,F403
