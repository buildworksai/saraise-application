# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Timeout & Duration Helper Functions
# backend/src/helpers/timeout_helpers.py
# Reference: docs/architecture/authentication-and-session-management-spec.md § 3.2

import os

def get_session_timeout() -> int:
    """Get session timeout in seconds.
    
    CRITICAL: Session timeout enforced server-side by SessionCookieManager.
    See docs/architecture/authentication-and-session-management-spec.md § 3.2.
    """
    return int(os.getenv('SESSION_TIMEOUT', '7200'))

def get_api_timeout() -> int:
    """Get API timeout in seconds"""
    return int(os.getenv('API_TIMEOUT', '30'))

def get_toast_duration(severity: str) -> int:
    """Get toast duration based on severity"""
    durations = {
        'info': int(os.getenv('TOAST_INFO_DURATION', '6')),
        'warning': int(os.getenv('TOAST_WARNING_DURATION', '8')),
        'error': int(os.getenv('TOAST_ERROR_DURATION', '10'))
    }
    return durations.get(severity, 6)

def get_timeout_config() -> dict:
    """Get all timeout configuration as dictionary"""
    return {
        'session': get_session_timeout(),
        'api': get_api_timeout(),
        'database': int(os.getenv('DATABASE_TIMEOUT', '30')),
        'redis': int(os.getenv('REDIS_TIMEOUT', '5')),
        'toast': {
            'info': get_toast_duration('info'),
            'warning': get_toast_duration('warning'),
            'error': get_toast_duration('error')
        }
    }

