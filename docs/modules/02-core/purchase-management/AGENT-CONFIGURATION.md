# Purchase Management Module - AI Agent Configuration

## Overview

The Purchase Management module exposes AI agents for intelligent supplier selection and purchase optimization. These agents are automatically discovered by Ask Amani and can be invoked through the SARAISE AI Assistant interface.

## Registered AI Agents

### 1. Supplier Selection Agent (`supplier_selection_agent`)

**Description:** AI agent for supplier selection and performance analysis

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.3
- **Max Tokens:** 1000

**Use Cases:**
- Analyze supplier performance metrics
- Recommend best suppliers for specific items
- Evaluate supplier proposals
- Identify supplier risks
- Compare supplier quotes

**Integration Points:**
- RFQ (Request for Quotation) workflows
- Supplier evaluation
- Purchase requisition processing
- Vendor management

**Ask Amani Entry Points:**
- "Which supplier should I choose for this item?"
- "Analyze supplier performance"
- "Compare supplier quotes"
- "Evaluate this supplier proposal"

### 2. Purchase Optimization Agent (`purchase_optimization_agent`)

**Description:** AI agent for purchase order optimization and cost analysis

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.2
- **Max Tokens:** 800

**Use Cases:**
- Optimize purchase order quantities
- Analyze purchase costs
- Identify cost savings opportunities
- Recommend bulk purchase opportunities
- Analyze purchase patterns

**Integration Points:**
- Purchase order creation
- Cost analysis
- Budget optimization
- Inventory planning

**Ask Amani Entry Points:**
- "Optimize this purchase order"
- "Analyze purchase costs"
- "Find cost savings opportunities"
- "Recommend purchase quantities"

## Workflows

### 1. Requisition to PO Workflow (`requisition_to_po`)

**Description:** Convert purchase requisition to purchase order workflow

**Steps:**
1. Data Ingestion: Extract requisition data
2. Validation: Verify approval and budget requirements
3. Data Transformation: Map requisition to purchase order
4. Data Output: Create purchase order record

**AI Agent Integration:**
- Uses `supplier_selection_agent` for supplier recommendation
- Uses `purchase_optimization_agent` for order optimization
- Automatically triggers on requisition approval

### 2. PO to GRN to Invoice Workflow (`po_to_grn_to_invoice`)

**Description:** Three-way matching workflow (PO, GRN, Invoice)

**Steps:**
1. Data Ingestion: Extract purchase order data
2. Validation: Verify GRN match, invoice match, and quantity match
3. Approval Workflow: Single-level approval
4. Data Output: Create approved invoice

**AI Agent Integration:**
- Uses `purchase_optimization_agent` for cost validation
- Automatically triggers on invoice receipt

## Ask Amani Integration

All Purchase Management AI agents are automatically discoverable by Ask Amani through the module registry. Users can interact with these agents through natural language queries:

**Example Queries:**
- "Which supplier should I choose for office supplies?"
- "Analyze supplier performance for the last quarter"
- "Optimize this purchase order"
- "Find cost savings opportunities in purchases"
- "Compare supplier quotes for this item"

## Configuration

AI agents are configured in `MODULE_MANIFEST` in `backend/src/modules/purchase/__init__.py`. To modify agent configurations:

1. Update the `ai_agents` array in `MODULE_MANIFEST`
2. Restart the application to reload module configuration
3. Ask Amani will automatically discover the updated agents

## Customization

AI agents can be customized through:
- Server Scripts: Modify agent behavior programmatically
- Client Scripts: Customize agent UI interactions
- Webhooks: Integrate with external procurement systems
- Custom API Endpoints: Expose agent functionality via REST APIs

See `CUSTOMIZATION.md` for detailed customization options.
