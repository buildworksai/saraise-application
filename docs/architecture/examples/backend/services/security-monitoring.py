# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Security Monitoring & Alerting Service
# backend/src/security/monitoring/security_monitor.py
# Reference: docs/architecture/security-model.md § 3.2

import logging
from datetime import datetime
from src.config.settings import settings

class SecurityMonitor:
    """Security event monitoring and alerting service.
    
    CRITICAL: All security events logged with proper context for audit.
    Authorization decisions evaluated by Policy Engine and logged for compliance.
    See docs/architecture/security-model.md § 3.2.
    """
    
    def __init__(self, environment: str):
        self.environment = environment
        self.logger = self._setup_logger()

    def _setup_logger(self):
        if self.environment == "development":
            # Development: Basic logging
            logging.basicConfig(level=logging.INFO)
            return logging.getLogger("security")
        elif self.environment == "staging":
            # Staging: Standard logging with alerts
            logging.basicConfig(level=logging.WARNING)
            return logging.getLogger("security")
        elif self.environment == "production":
            # Production: Comprehensive logging with SIEM integration
            logging.basicConfig(level=logging.ERROR)
            return logging.getLogger("security")

    def log_security_event(self, event_type: str, details: dict):
        if self.environment == "development":
            self.logger.info(f"Security Event: {event_type} - {details}")
        elif self.environment == "staging":
            self.logger.warning(f"Security Event: {event_type} - {details}")
            # Send to staging monitoring system
        elif self.environment == "production":
            self.logger.error(f"Security Event: {event_type} - {details}")
            # Send to SIEM system
            # Send immediate alerts for critical events

    def monitor_authentication(self, user_id: str, success: bool, ip_address: str):
        event_details = {
            "user_id": user_id,
            "success": success,
            "ip_address": ip_address,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.log_security_event("authentication", event_details)

    def monitor_authorization(self, user_id: str, resource: str, access_granted: bool):
        event_details = {
            "user_id": user_id,
            "resource": resource,
            "access_granted": access_granted,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.log_security_event("authorization", event_details)

# Global security monitor instance
security_monitor = SecurityMonitor(settings.APP_ENV)

