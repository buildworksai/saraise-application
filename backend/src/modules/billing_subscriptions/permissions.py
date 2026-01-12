"""
BillingSubscriptions Permissions.

Defines permissions for the BillingSubscriptions module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "billing_subscriptions.resource:create",
    "billing_subscriptions.resource:read",
    "billing_subscriptions.resource:update",
    "billing_subscriptions.resource:delete",
    "billing_subscriptions.resource:activate",
    "billing_subscriptions.resource:deactivate",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "billing_subscriptions.resource:create",
    "billing_subscriptions.resource:delete",
]
