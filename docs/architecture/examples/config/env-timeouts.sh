# ✅ APPROVED: Environment Variables for Timeouts & Durations
# Reference: docs/architecture/authentication-and-session-management-spec.md § 3.2
#            docs/architecture/operational-runbooks.md § 1

# CRITICAL: Session timeout enforced server-side via Redis expiration
# See docs/architecture/authentication-and-session-management-spec.md § 3.2

# Session & Authentication Timeouts
SESSION_TIMEOUT=7200                    # 2 hours in seconds
SESSION_REFRESH_THRESHOLD=1800         # 30 minutes before expiry
PASSWORD_RESET_TIMEOUT=3600            # 1 hour for password reset
MFA_TIMEOUT=300                        # 5 minutes for MFA codes

# API & Request Timeouts
API_TIMEOUT=30                         # 30 seconds for API calls
REQUEST_TIMEOUT=60                     # 60 seconds for HTTP requests
DATABASE_TIMEOUT=30                    # 30 seconds for DB queries
REDIS_TIMEOUT=5                        # 5 seconds for Redis operations

# UI & Notification Timeouts
TOAST_INFO_DURATION=6                  # 6 seconds for info toasts
TOAST_WARNING_DURATION=8               # 8 seconds for warning toasts
TOAST_ERROR_DURATION=10                # 10 seconds for error toasts
LOADING_TIMEOUT=15                     # 15 seconds for loading states

# Background Job Timeouts
JOB_TIMEOUT=3600                       # 1 hour for background jobs
CLEANUP_INTERVAL=86400                 # 24 hours for cleanup jobs
HEALTH_CHECK_INTERVAL=60               # 1 minute for health checks

