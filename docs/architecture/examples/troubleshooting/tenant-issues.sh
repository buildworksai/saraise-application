#!/bin/bash
# ✅ APPROVED: Multi-Tenant Troubleshooting Commands
# Reference: docs/architecture/application-architecture.md § 4.1 (Row-Level Multitenancy)
# Also: docs/architecture/operational-runbooks.md § 2 (Troubleshooting)
# 
# CRITICAL NOTES:
# - Row-Level Multitenancy enforced: ALL queries include tenant_id filtering
# - Tenant isolation breaches are CRITICAL security incidents
# - Module installations per-tenant controlled by subscription plans
# - Session tenant_id must match database row tenant_id (implicit filtering)

# Problem: Tenant isolation failures
# Symptoms
# - Users seeing other tenants' data
# - "Invalid tenant access" errors
# - Cross-tenant data leakage

# Diagnosis
# 1. Check tenant_id in requests
# 2. Verify tenant validation logic
# 3. Check database queries
# 4. Validate user-tenant associations

# Solutions
# Check tenant validation
grep -r "validate_tenant_context" backend/src/

# Verify user-tenant associations
psql -h localhost -p 5432 -U postgres -d saraise -c "SELECT id, email, tenant_id FROM users;"

# Check tenant isolation mode
echo $TENANT_ISOLATION_MODE

# Test tenant isolation (session cookie automatically included)
curl -b cookies.txt -H "X-Tenant-ID: tenant-1" http://localhost:30000/agents

