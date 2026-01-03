# Inventory Management - AI Agent Configuration

## Overview

The Inventory Management module exposes AI agents for inventory optimization and stock auditing. These agents are automatically discovered by Ask Amani and can be invoked through the SARAISE AI Assistant interface.

## Registered AI Agents

### 1. Inventory Optimization Agent (`inventory_optimization_agent`)

**Description:** AI agent for inventory optimization, safety stock calculation, and replenishment recommendations.

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.2
- **Max Tokens:** 1000

**Use Cases:**
- Calculate optimal safety stock levels based on demand variability
- Recommend reorder points and quantities
- Identify slow-moving and obsolete inventory (SLOB)
- Forecast future inventory needs

**Integration Points:**
- Stock balance monitoring
- Purchase requisition generation
- Forecasting service

**Ask Amani Entry Points:**
- "Optimize inventory for Item X"
- "What items need reordering?"
- "Show me slow-moving items"
- "Calculate safety stock for current demand"

### 2. Stock Audit Agent (`stock_audit_agent`)

**Description:** AI agent for detecting stock anomalies and reconciling physical vs system stock.

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.1
- **Max Tokens:** 800

**Use Cases:**
- Detect unexplainable stock variances
- Reconcile physical count data with system records
- Identify potential shrinkage or theft patterns
- Suggest cycle count priorities

**Integration Points:**
- Stock Entry (Physical Inventory)
- Stock Ledger
- Audit logging

**Ask Amani Entry Points:**
- "Analyze stock variance for Item Y"
- "Reconcile physical count scan"
- "Where are the biggest stock discrepancies?"

## Ask Amani Integration

All Inventory AI agents are automatically discoverable by Ask Amani.

**Example Queries:**
- "How much safety stock do I need for laptops?"
- "Analyze inventory discrepancies for Warehouse A"

## Configuration

AI agents are configured in `MODULE_MANIFEST` in `backend/src/modules/inventory/__init__.py`.
