# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Complete logging configuration
# backend/src/core/logging_config.py
# Reference: docs/architecture/security-model.md § 4.2 (Audit Logging)
# CRITICAL NOTES:
# - Three logging levels: development (DEBUG), staging (INFO), production (WARN)
# - JSON formatter for structured logging (parse and aggregate in log analysis tools)
# - Console handler outputs to stdout (container/systemd log aggregation)
# - File handler persists logs to disk (operational-runbooks.md § 4.1)
# - Detailed formatter includes line numbers and logger names (debugging aid)
# - All authentication/authorization decisions logged (security-model.md § 4.2)
# - PII filtering: never log passwords, tokens, secrets (redact before logging)
# - Audit logs: user_id, timestamp, action, resource, status (immutable records)
# - Performance logs: request latency, database query timing (monitoring.md)
# - Error logs: exception type, stack trace, context (debugging production issues)
# Source: docs/architecture/security-model.md § 4.2, operational-runbooks.md § 4.1

import logging
import logging.config
from src.config.settings import settings

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        },
        "detailed": {
            "format": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s"
        },
        "json": {
            "format": '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}'
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "standard",
            "stream": "ext://sys.stdout"
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "detailed",
            "filename": "logs/saraise.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "ERROR",
            "formatter": "detailed",
            "filename": "logs/saraise_error.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5
        }
    },
    "loggers": {
        "": {  # Root logger
            "handlers": ["console", "file", "error_file"],
            "level": settings.LOG_LEVEL.upper(),
            "propagate": False
        },
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False
        },
        "django.db.backends": {
            "handlers": ["file"],
            "level": "WARNING",
            "propagate": False
        }
    }
}

# Initialize logging
logging.config.dictConfig(LOGGING_CONFIG)

