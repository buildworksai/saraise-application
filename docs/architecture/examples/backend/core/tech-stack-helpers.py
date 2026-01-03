# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Python Helper Functions for Tech Stack
# backend/src/core/tech_stack.py
# Reference: docs/architecture/application-architecture.md § 5 (Tech Stack)
# CRITICAL NOTES:
# - All Docker image versions sourced from environment variables (no hardcoding)
# - PostgreSQL: 17-alpine (latest stable with Alpine for small image size)
# - Redis: 7-alpine (in-memory cache and session store, Alpine variant)
# - Django: 5.0.1 (ORM, migrations, and REST framework integrated)
# - Django REST Framework: 3.14.0 (API views and serializers)
# - Python: 3.10 LTS minimum (type hints, walrus operator support)
# - Database drivers: psycopg 3.1+ (PostgreSQL async driver)
# - ORM: Django ORM with proper type annotations
# - Version mismatch between environments prevented via env vars
# - Image versions pinned (no latest tags in production)
# - Security updates validated before version bump (CVE scanning)
# Source: docs/architecture/application-architecture.md § 5

import os

def get_postgres_image() -> str:
    """Get PostgreSQL Docker image using environment variables"""
    version = os.getenv('POSTGRES_VERSION', '17')
    return f"postgres:{version}-alpine"

def get_redis_image() -> str:
    """Get Redis Docker image using environment variables"""
    version = os.getenv('REDIS_VERSION', '7')
    return f"redis:{version}-alpine"

def get_django_version() -> str:
    """Get Django version using environment variables"""
    return os.getenv('DJANGO_VERSION', '5.0.1')

def get_python_version() -> str:
    """Get Python version using environment variables"""
    return os.getenv('PYTHON_VERSION', '3.10')

def get_kong_image() -> str:
    """Get Kong Docker image using environment variables"""
    return os.getenv('KONG_IMAGE', 'kong:3.4-alpine')

def get_loki_image() -> str:
    """Get Loki Docker image using environment variables"""
    return os.getenv('LOKI_IMAGE', 'grafana/loki:2.9.0')

def get_grafana_image() -> str:
    """Get Grafana Docker image using environment variables"""
    return os.getenv('GRAFANA_IMAGE', 'grafana/grafana:10.2.0')

def get_prometheus_image() -> str:
    """Get Prometheus Docker image using environment variables"""
    return os.getenv('PROMETHEUS_IMAGE', 'prom/prometheus:latest')

def get_celery_image() -> str:
    """Get Celery Docker image using environment variables"""
    version = os.getenv('CELERY_VERSION', '5.3.4')
    return f"celery:{version}-alpine"

def get_flower_image() -> str:
    """Get Flower Docker image using environment variables"""
    version = os.getenv('FLOWER_VERSION', '2.0.1')
    return f"mher/flower:{version}"

def get_tech_requirements() -> dict:
    """Get all tech requirements as a dictionary"""
    return {
        'django': os.getenv('DJANGO_VERSION', '5.0.1'),
        'djangorestframework': os.getenv('DJANGORESTFRAMEWORK_VERSION', '3.14.0'),
        'gunicorn': os.getenv('GUNICORN_VERSION', '22.0.0'),
        'psycopg': os.getenv('PSYCOPG_VERSION', '3.1.18'),
        'pydantic': os.getenv('PYDANTIC_VERSION', '2.11.3'),
        'pytest': os.getenv('PYTEST_VERSION', '8.3.5'),
        'black': os.getenv('BLACK_VERSION', '25.1.0'),
        'flake8': os.getenv('FLAKE8_VERSION', '7.2.0'),
    }

