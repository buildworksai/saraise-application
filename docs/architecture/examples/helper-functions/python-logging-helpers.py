# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Logging & Monitoring Helper Functions
# backend/src/helpers/logging_helpers.py
# Reference: docs/architecture/security-model.md § 4.2 (Audit Logging)

import os
import logging

def get_log_level() -> str:
    """Get log level based on environment.
    
    CRITICAL: Log level must include authorization decisions.
    All sensitive operations must be audited.
    See docs/architecture/security-model.md § 4.2.
    """
    env = os.getenv('APP_ENV', 'development')
    level_map = {
        'development': os.getenv('LOG_LEVEL_DEVELOPMENT', 'DEBUG'),
        'staging': os.getenv('LOG_LEVEL_STAGING', 'INFO'),
        'production': os.getenv('LOG_LEVEL_PRODUCTION', 'WARN')
    }
    return level_map.get(env, 'INFO')

def get_log_format() -> str:
    """Get log format"""
    return os.getenv('LOG_FORMAT', 'json')

def get_monitoring_config() -> dict:
    """Get monitoring configuration"""
    return {
        'prometheus': {
            'enabled': os.getenv('PROMETHEUS_ENABLED', 'true').lower() == 'true',
            'port': int(os.getenv('PROMETHEUS_PORT', '19090'))
        },
        'grafana': {
            'enabled': os.getenv('GRAFANA_ENABLED', 'true').lower() == 'true',
            'port': int(os.getenv('GRAFANA_PORT', '13000'))
        },
        'jaeger': {
            'enabled': os.getenv('JAEGER_ENABLED', 'false').lower() == 'true',
            'endpoint': os.getenv('JAEGER_ENDPOINT', 'http://localhost:14268/api/traces')
        },
        'health_check': {
            'interval': int(os.getenv('HEALTH_CHECK_INTERVAL', '60')),
            'timeout': int(os.getenv('HEALTH_CHECK_TIMEOUT', '30')),
            'retries': int(os.getenv('HEALTH_CHECK_RETRIES', '3'))
        }
    }

