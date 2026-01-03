<!-- SPDX-License-Identifier: Apache-2.0 -->
# Workflow Automation Module

**Module Code**: `workflow_automation`
**Category**: AI Automation
**Priority**: Critical - Core Automation Infrastructure
**Version**: 1.0.0
**Status**: Production Ready

---

## Executive Summary

The Workflow Automation module provides visual workflow builder, state machines, conditional branching, and integration with AI agents for enterprise automation. It enables users to create, deploy, and monitor complex business processes with visual drag-and-drop interface and AI-powered optimization.

### Vision

**"Visualize, automate, optimize - every business process at your fingertips."**

---

## Core Features

- **Visual Workflow Builder**: Drag-and-drop interface for creating workflows
- **State Machine Engine**: Robust state management and transitions
- **Conditional Branching**: Complex decision trees and routing
- **Event-Driven Triggers**: React to system events, webhooks, schedules
- **AI Agent Integration**: Embed AI agents as workflow steps
- **Workflow Templates**: Pre-built templates for common processes
- **Execution Monitoring**: Real-time execution tracking and analytics
- **Error Handling**: Automatic retries, error recovery, escalation

---

## Customization Framework Integration

The Workflow Automation module is fully integrated with the SARAISE Customization Framework, allowing extensive customization without modifying core code.

### Customization Points

- **Server Scripts**: Customize workflow behavior on lifecycle events (before_insert, after_save, validate, etc.)
- **Client Scripts**: Enhance workflow builder UI with custom validations and UI improvements
- **Webhooks**: Trigger external systems on workflow events (execution started, completed, failed, step completed)
- **Custom API Endpoints**: Extend the API with custom workflow operations
- **Event Bus Integration**: Subscribe to workflow events for custom processing

### Documentation

For complete customization documentation, see:
- **[Customization Guide](./CUSTOMIZATION.md)** - Comprehensive guide to all customization points
- **[Customization Framework](../../01-foundation/customization-framework/README.md)** - Framework overview

### Demo Customizations

Example customizations are available in:
- `backend/scripts/demo_customizations/workflow_automation/` - Demo server scripts and webhooks

---

## Database Migrations

### Migration Structure

The Workflow Automation module uses Django migrations located in:
- `backend/src/modules/workflow_automation/migrations/`

### Key Migrations

- **001_initial.py**: Creates core tables (`workflows`, `workflow_steps`, `workflow_templates`, `workflow_executions`) with `tenant_id` isolation
- **002_add_agent_fks.py**: Adds foreign key constraints to `ai_agents` table with proper tenant filtering

### Critical Tables

The following tables are marked as critical in `migration_categories.py`:
- `workflows` - Core workflow definitions
- `workflow_steps` - Individual workflow steps
- `workflow_templates` - Workflow template library
- `workflow_executions` - Execution tracking and audit logs

### Indexes

Comprehensive indexes are created on:
- Foreign keys: `tenant_id`, `workflow_id`, `ai_agent_id`, `created_by`
- Frequently queried fields: `status`, `trigger_type`, `is_active`, `created_at`
- Composite indexes for common query patterns (workflow_id + step_order)

### Migration Dependencies

- Depends on: `004_inventory_advanced` (base dependency)
- Branch label: `workflow_automation`
- Cross-module dependencies: References `ai_agents` table from AI Agent Management module

---

## Documentation

- **Design Document Part 1**: See `WORKFLOW-AUTOMATION-DESIGN.md`
- **Design Document Part 2**: See `WORKFLOW-AUTOMATION-DESIGN-PART2.md`
- **Customization Guide**: See `CUSTOMIZATION.md`

---

## Dependencies

### Required Modules
- `base` - Core platform functionality
- `auth` - Authentication and authorization
- `metadata` - Metadata modeling framework
- `ai_agent_management` - AI agent integration

### Optional Modules
- `automation` - Advanced orchestration capabilities
- `analytics` - Workflow performance analytics
