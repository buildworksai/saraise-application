# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ❌ WRONG: MODULE_MANIFEST as Python dict (deprecated pattern)
# ✅ CORRECT: Use manifest.yaml file per module
# Reference: docs/architecture/module-framework.md § 3
# Reference: .agents/rules/15-module-architecture.md

# File: backend/src/modules/finance-ledger/manifest.yaml
"""
name: finance-ledger
version: 1.3.0
description: General Ledger and posting engine
type: domain
lifecycle: managed

# Module dependencies (required modules)
dependencies:
  - core-identity >=1.0
  - core-workflow >=1.0
  - finance-accounting >=2.0

# Permissions declared by this module
permissions:
  - finance.ledger:create
  - finance.ledger:edit
  - finance.ledger:post
  - finance.ledger:view
  - finance.ledger:delete

# Segregation of Duties (SoD) actions
# Users with conflicting actions cannot have both assigned
sod_actions:
  - finance.ledger:create
  - finance.ledger:approve
  - finance.ledger:post

# Search indexes for this module
search_indexes:
  - finance_ledger_entries
  - finance_journal_entries

# AI tools exposed by this module
ai_tools:
  - post_journal_entry
  - reconcile_accounts
  
# External dependencies
external_dependencies:
  python:
    - openpyxl>=3.0.0  # For Excel export

metadata:
  author: SARAISE
  license: Apache-2.0
  category: finance
  website: https://github.com/buildworksai/saraise
"""

# Module structure:
# backend/src/modules/finance-ledger/
#   manifest.yaml          # Module contract (this file)
#   models.py             # Django ORM models
#   api.py                # DRF ViewSets
#   services.py           # Business logic
#   permissions.py        # Permission definitions
#   policies.py           # Policy Engine rules
#   workflows.py          # Workflow definitions
#   search.py             # Search index configuration
#   migrations/           # Django migrations migrations
#   tests/                # Module tests

# Module access controlled by ModuleAccessMiddleware
# - Checks TenantModule table for per-tenant installation
# - Returns 403 if tenant doesn't have module installed
# - Authorization decisions evaluated by Policy Engine (not cached)

