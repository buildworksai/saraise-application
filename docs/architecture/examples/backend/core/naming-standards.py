# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Naming Standards Helper Functions
# backend/src/core/naming_standards.py
# Reference: docs/architecture/application-architecture.md § 1 (Naming Conventions)
# CRITICAL NOTES:
# - All names sourced from environment variables (no hardcoding)
# - Company/product names consistent across frontend, backend, infrastructure
# - Database naming: saraise (base), saraise_dev, saraise_staging, saraise_prod (per-environment)
# - Container names: api, ui, db, redis (kebab-case convention)
# - Network names: saraise-dev, saraise-staging, saraise-prod (docker-compose networks)
# - API routes use kebab-case (/api/v1/my-resource)
# - Internal code uses snake_case (function names, variables)
# - User-facing text uses Title Case (menu items, labels)
# - Environment identifiers: development, staging, production (lowercase)
# - Consistency maintained via environment variables (prevents drift)
# Source: docs/architecture/application-architecture.md § 1

import os

def get_naming_standards() -> dict:
    """Get all naming standards"""
    return {
        'company': {
            'name': os.getenv('COMPANY_NAME', 'SARAISE'),
            'product': os.getenv('PRODUCT_NAME', 'SARAISE'),
            'full_name': os.getenv('FULL_PRODUCT_NAME', 'SARAISE - Secure and Reliable AI Symphony ERP'),
            'short_name': os.getenv('SHORT_NAME', 'SARAISE')
        },
        'database': {
            'name': os.getenv('DATABASE_NAME', 'saraise'),
            'dev': os.getenv('DATABASE_DEV_NAME', 'saraise_dev'),
            'staging': os.getenv('DATABASE_STAGING_NAME', 'saraise_staging'),
            'prod': os.getenv('DATABASE_PROD_NAME', 'saraise_prod')
        },
        'containers': {
            'frontend': os.getenv('CONTAINER_FRONTEND', 'ui'),
            'backend': os.getenv('CONTAINER_BACKEND', 'api'),
            'database': os.getenv('CONTAINER_DATABASE', 'db'),
            'redis': os.getenv('CONTAINER_REDIS', 'redis'),
            'minio': os.getenv('CONTAINER_MINIO', 'minio'),
            'vault': os.getenv('CONTAINER_VAULT', 'vault'),
            'mailhog': os.getenv('CONTAINER_MAILHOG', 'mailhog')
        },
        'networks': {
            'dev': os.getenv('NETWORK_DEV', 'saraise-dev'),
            'staging': os.getenv('NETWORK_STAGING', 'saraise-staging'),
            'prod': os.getenv('NETWORK_PROD', 'saraise-prod')
        }
    }

def get_database_name(env: str = 'development') -> str:
    """Get database name for environment"""
    standards = get_naming_standards()
    env_map = {
        'development': standards['database']['dev'],
        'staging': standards['database']['staging'],
        'production': standards['database']['prod']
    }
    return env_map.get(env, standards['database']['name'])

def get_container_name(service: str) -> str:
    """Get container name for service"""
    standards = get_naming_standards()
    return standards['containers'].get(service, service)

def get_network_name(env: str = 'development') -> str:
    """Get network name for environment"""
    standards = get_naming_standards()
    env_map = {
        'development': standards['networks']['dev'],
        'staging': standards['networks']['staging'],
        'production': standards['networks']['prod']
    }
    return env_map.get(env, standards['networks']['dev'])

