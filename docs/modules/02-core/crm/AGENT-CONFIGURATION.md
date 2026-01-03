# Customer Relationship Management - AI Agent Configuration

## Overview

The CRM module exposes AI agents for intelligent lead scoring and customer sentiment analysis. These agents are automatically discovered by Ask Amani and can be invoked through the SARAISE AI Assistant interface.

## Registered AI Agents

### 1. Lead Scoring Agent (`lead_scoring_agent`)

**Description:** AI agent for scoring leads based on behavior, demographic profile, and interaction history.

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.7
- **Max Tokens:** 1000

**Use Cases:**
- Automatically score new leads upon creation
- Re-score leads after significant activities (e.g., email open, website visit)
- Prioritize leads for sales representatives
- Identify "hot" leads ready for conversion

**Integration Points:**
- Lead processing workflows
- Sales pipeline management
- Marketing automation triggers

**Ask Amani Entry Points:**
- "Score this lead"
- "Why is this lead score low?"
- "Show me top-scoring leads"

### 2. Customer Sentiment Agent (`customer_sentiment_agent`)

**Description:** AI agent for analyzing customer sentiment from interaction logs, emails, and notes.

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.5
- **Max Tokens:** 500

**Use Cases:**
- Analyze sentiment of latest emails or call notes
- Detect customers at risk of churn
- Identify happy customers for testimonials
- Aggregate overall portfolio sentiment

**Integration Points:**
- Activity logging
- Customer health dashboard
- Customer support ticket analysis

**Ask Amani Entry Points:**
- "Analyze sentiment for this customer"
- "Is this customer happy?"
- "Summarize recent interactions"

## Workflows

### 1. Lead to Opportunity (`lead_to_opportunity`)

**Description:** Convert lead to opportunity workflow.

**Steps:**
1. Data Ingestion: Lead data
2. Validation: Check email and company presence
3. Data Transformation: Map fields to Opportunity
4. Data Output: Create Opportunity record

**AI Agent Integration:**
- Can trigger `lead_scoring_agent` before conversion to ensure quality.

### 2. Opportunity to Customer (`opportunity_to_customer`)

**Description:** Convert opportunity to customer workflow.

**Steps:**
1. Data Ingestion: Opportunity data
2. Validation: Check if status is "Won"
3. Data Transformation: Map fields to Customer
4. Data Output: Create Customer record

## Ask Amani Integration

All CRM AI agents are automatically discoverable by Ask Amani.

**Example Queries:**
- "Score lead John Doe"
- "Analyze sentiment for Acme Corp"
- "Convert this lead to an opportunity"
- "What is the sentiment trend for my accounts?"

## Configuration

AI agents are configured in `MODULE_MANIFEST` in `backend/src/modules/crm/__init__.py`.

## Customization

See `CUSTOMIZATION.md` for details on how to extend agent behaviors using server scripts or custom endpoints.
