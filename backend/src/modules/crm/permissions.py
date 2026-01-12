"""CRM Permissions.

Defines permissions for the CRM module.
"""

from typing import List

# Permission declarations
PERMISSIONS: List[str] = [
    "crm.lead:create",
    "crm.lead:read",
    "crm.lead:update",
    "crm.lead:delete",
    "crm.account:create",
    "crm.account:read",
    "crm.account:update",
    "crm.account:delete",
    "crm.contact:create",
    "crm.contact:read",
    "crm.contact:update",
    "crm.contact:delete",
    "crm.opportunity:create",
    "crm.opportunity:read",
    "crm.opportunity:update",
    "crm.opportunity:delete",
    "crm.activity:create",
    "crm.activity:read",
    "crm.activity:update",
    "crm.activity:delete",
    "crm.forecasting:read",
]

# SoD (Segregation of Duties) actions
SOD_ACTIONS: List[str] = [
    "crm.opportunity:create",
    "crm.opportunity:update",
]
