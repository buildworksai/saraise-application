"""Minimal Django settings for running this foundation unit in isolation."""

SECRET_KEY = "async-jobs-unit-tests-only"  # pragma: allowlist secret
INSTALLED_APPS = ["src.core.async_jobs"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
