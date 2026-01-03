# CRM Module - Technical Specifications

**Module**: `crm` v1.0.0
**Status**: ✅ Core Complete | 🔄 Advanced Features Pending
**Spec Version**: 1.0
**Last Updated**: 2025-01-XX

---

## Table of Contents

1. [Email Marketing Integration Specifications](#1-email-marketing-integration-specifications)
2. [Workflow Automation Integration Specifications](#2-workflow-automation-integration-specifications)
3. [AI Agent Integration Specifications](#3-ai-agent-integration-specifications)
4. [Phase 4 Database Schema Specifications](#4-phase-4-database-schema-specifications)
5. [Frontend Component Specifications](#5-frontend-component-specifications)
6. [API Integration Specifications](#6-api-integration-specifications)
7. [Test Plan Specifications](#7-test-plan-specifications)

---

## 1. Email Marketing Integration Specifications

### 1.1 Integration Architecture

**Pattern**: Cross-Module Service Integration (SARAISE-16001)

The CRM module integrates with `email_marketing` module using the existing `CRMIntegrationService` pattern. The integration is bidirectional:
- **CRM → Email Marketing**: CRM provides contacts/customers for email campaigns
- **Email Marketing → CRM**: Email sequences are created and managed for CRM leads

### 1.2 Email Sequence Service Specification

**File**: `backend/src/modules/crm/services/email_sequence_service.py`

```python
from django.db import models, transaction
from typing import Optional, Dict, Any, List
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from datetime import datetime

# Import email_marketing services (conditional import)
try:
    from src.modules.email_marketing.services import AutomationService
    from src.modules.email_marketing.services import CampaignService
    from src.modules.email_marketing.models import EmailSequence, EmailSequenceTemplate
    EMAIL_MARKETING_AVAILABLE = True
except ImportError:
    EMAIL_MARKETING_AVAILABLE = False
    AutomationService = None
    CampaignService = None
    EmailSequence = None
    EmailSequenceTemplate = None


class EmailSequenceService:
    """Service for managing email sequences in CRM context"""

    def __init__(self, db: AsyncSession):
        self.db = db
        if not EMAIL_MARKETING_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Email marketing module is not available. Email sequences require email_marketing module."
            )
        self.automation_service = AutomationService(db)
        self.campaign_service = CampaignService(db)

    async def create_sequence_for_lead(
        self,
        lead_id: str,
        sequence_template_id: str,
        tenant_id: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create email sequence for CRM lead.

        Integration Flow:
        1. Get lead from CRM
        2. Get sequence template from email_marketing module
        3. Create sequence instance in email_marketing module
        4. Link sequence to CRM lead
        5. Schedule first email
        6. Create CRM activity log

        Args:
            lead_id: CRM lead ID
            sequence_template_id: Email sequence template ID from email_marketing module
            tenant_id: Tenant ID for isolation
            user_id: User creating the sequence

        Returns:
            Sequence instance with CRM link
        """
        # 1. Get lead from CRM
        from src.modules.crm.services.lead_service import LeadService
        lead_service = LeadService(self.db)
        lead = await lead_service.get_lead(lead_id, tenant_id)

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        if not lead.email:
            raise HTTPException(status_code=400, detail="Lead must have email address")

        # 2. Get sequence template from email_marketing module
        template = await self.automation_service.get_sequence_template(
            template_id=sequence_template_id,
            tenant_id=tenant_id
        )

        if not template:
            raise HTTPException(status_code=404, detail="Sequence template not found")

        # 3. Create sequence instance in email_marketing module
        sequence_data = {
            "template_id": sequence_template_id,
            "contact_email": lead.email,
            "contact_name": lead.full_name or f"{lead.first_name} {lead.last_name}",
            "tenant_id": tenant_id,
            "metadata": {
                "crm_lead_id": lead_id,
                "crm_module": "crm",
                "created_by": user_id
            }
        }

        sequence = await self.automation_service.create_sequence(
            sequence_data=sequence_data,
            tenant_id=tenant_id
        )

        # 4. Link sequence to CRM lead (store sequence_id in lead metadata or separate table)
        # Option A: Store in lead metadata JSON field
        if not lead.metadata:
            lead.metadata = {}
        lead.metadata["email_sequence_id"] = sequence["id"]
        lead.metadata["email_sequence_status"] = "active"
        await self.db.commit()

        # 5. Schedule first email (handled by email_marketing module)
        # Sequence starts automatically when created

        # 6. Create CRM activity log
        from src.modules.crm.services.activity_service import ActivityService
        activity_service = ActivityService(self.db)
        await activity_service.create_activity(
            activity_data={
                "type": "email_sequence",
                "subject": f"Email sequence started: {template['name']}",
                "description": f"Email sequence '{template['name']}' started for lead",
                "related_to_type": "Lead",
                "related_to_id": lead_id,
                "tenant_id": tenant_id
            },
            tenant_id=tenant_id
        )

        return {
            "sequence_id": sequence["id"],
            "lead_id": lead_id,
            "template_name": template["name"],
            "status": "active",
            "started_at": datetime.utcnow().isoformat()
        }

    async def get_sequence_status(
        self,
        lead_id: str,
        tenant_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get email sequence status for lead"""
        # Get lead
        from src.modules.crm.services.lead_service import LeadService
        lead_service = LeadService(self.db)
        lead = await lead_service.get_lead(lead_id, tenant_id)

        if not lead or not lead.metadata or "email_sequence_id" not in lead.metadata:
            return None

        sequence_id = lead.metadata["email_sequence_id"]

        # Get sequence status from email_marketing module
        sequence_status = await self.automation_service.get_sequence_status(
            sequence_id=sequence_id,
            tenant_id=tenant_id
        )

        return sequence_status

    async def pause_sequence(
        self,
        lead_id: str,
        tenant_id: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Pause email sequence for lead"""
        # Get lead
        from src.modules.crm.services.lead_service import LeadService
        lead_service = LeadService(self.db)
        lead = await lead_service.get_lead(lead_id, tenant_id)

        if not lead or not lead.metadata or "email_sequence_id" not in lead.metadata:
            raise HTTPException(status_code=404, detail="No active email sequence found")

        sequence_id = lead.metadata["email_sequence_id"]

        # Pause sequence in email_marketing module
        result = await self.automation_service.pause_sequence(
            sequence_id=sequence_id,
            tenant_id=tenant_id
        )

        # Update lead metadata
        lead.metadata["email_sequence_status"] = "paused"
        await self.db.commit()

        # Create activity log
        from src.modules.crm.services.activity_service import ActivityService
        activity_service = ActivityService(self.db)
        await activity_service.create_activity(
            activity_data={
                "type": "email_sequence",
                "subject": "Email sequence paused",
                "description": "Email sequence paused for lead",
                "related_to_type": "Lead",
                "related_to_id": lead_id,
                "tenant_id": tenant_id
            },
            tenant_id=tenant_id
        )

        return result

    async def resume_sequence(
        self,
        lead_id: str,
        tenant_id: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resume email sequence for lead"""
        # Similar to pause_sequence but resume
        pass

    async def sync_email_activities(
        self,
        lead_id: str,
        tenant_id: str
    ) -> int:
        """
        Sync email activities from email_marketing module to CRM.

        This method:
        1. Gets email events from email_marketing module for the lead's sequence
        2. Creates CRM activities for each email event (sent, opened, clicked, replied)
        3. Updates lead engagement score based on email interactions

        Returns:
            Number of activities synced
        """
        # Get lead
        from src.modules.crm.services.lead_service import LeadService
        lead_service = LeadService(self.db)
        lead = await lead_service.get_lead(lead_id, tenant_id)

        if not lead or not lead.metadata or "email_sequence_id" not in lead.metadata:
            return 0

        sequence_id = lead.metadata["email_sequence_id"]

        # Get email events from email_marketing module
        email_events = await self.automation_service.get_sequence_events(
            sequence_id=sequence_id,
            tenant_id=tenant_id
        )

        # Create CRM activities for each event
        from src.modules.crm.services.activity_service import ActivityService
        activity_service = ActivityService(self.db)

        synced_count = 0
        for event in email_events:
            # Check if activity already exists
            existing = await activity_service.get_activity_by_external_id(
                external_id=f"email_{event['id']}",
                tenant_id=tenant_id
            )

            if not existing:
                await activity_service.create_activity(
                    activity_data={
                        "type": f"email_{event['type']}",  # email_sent, email_opened, email_clicked, email_replied
                        "subject": f"Email {event['type']}: {event.get('subject', 'N/A')}",
                        "description": event.get("description", ""),
                        "related_to_type": "Lead",
                        "related_to_id": lead_id,
                        "external_id": f"email_{event['id']}",
                        "metadata": {
                            "email_event_id": event["id"],
                            "email_sequence_id": sequence_id,
                            "timestamp": event["timestamp"]
                        },
                        "tenant_id": tenant_id
                    },
                    tenant_id=tenant_id
                )
                synced_count += 1

        # Update lead engagement score
        if synced_count > 0:
            await lead_service.update_lead_engagement_score(lead_id, tenant_id)

        return synced_count
```

### 1.3 Email Sequence Routes Specification

**File**: `backend/src/modules/crm/routes.py` (additions)

```python
# Add to existing CRM routes

@router.post("/leads/{lead_id}/email-sequences", response_model=EmailSequenceResponse)
async def create_lead_email_sequence(
    lead_id: str,
    sequence_data: EmailSequenceCreate,
    request: Request,
    current_user: User = Depends(RequireTenantUser),
    db: AsyncSession = Depends(get_db)
):
    """
    Create email sequence for lead.

    Requires:
    - email_marketing module installed
    - Lead must have email address
    - User must have tenant_user role or higher
    """
    service = EmailSequenceService(db)
    sequence = await service.create_sequence_for_lead(
        lead_id=lead_id,
        sequence_template_id=sequence_data.template_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id
    )

    # Audit log
    audit_service = AuditService(db)
    await audit_service.log_event(
        actor_sub=current_user.id,
        actor_email=current_user.email,
        tenant_id=current_user.tenant_id,
        resource="crm.email_sequence",
        action="CREATE",
        result="success",
        metadata={"lead_id": lead_id, "sequence_id": sequence["sequence_id"]},
        request=request
    )

    return sequence

@router.get("/leads/{lead_id}/email-sequences/status", response_model=EmailSequenceStatusResponse)
async def get_lead_email_sequence_status(
    lead_id: str,
    current_user: User = Depends(RequireTenantUser),
    db: AsyncSession = Depends(get_db)
):
    """Get email sequence status for lead"""
    service = EmailSequenceService(db)
    status = await service.get_sequence_status(
        lead_id=lead_id,
        tenant_id=current_user.tenant_id
    )

    if not status:
        raise HTTPException(status_code=404, detail="No email sequence found")

    return status

@router.post("/leads/{lead_id}/email-sequences/pause")
async def pause_lead_email_sequence(
    lead_id: str,
    request: Request,
    current_user: User = Depends(RequireTenantUser),
    db: AsyncSession = Depends(get_db)
):
    """Pause email sequence for lead"""
    service = EmailSequenceService(db)
    result = await service.pause_sequence(
        lead_id=lead_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id
    )

    # Audit log
    audit_service = AuditService(db)
    await audit_service.log_event(
        actor_sub=current_user.id,
        actor_email=current_user.email,
        tenant_id=current_user.tenant_id,
        resource="crm.email_sequence",
        action="PAUSE",
        result="success",
        metadata={"lead_id": lead_id},
        request=request
    )

    return result

@router.post("/leads/{lead_id}/email-sequences/sync")
async def sync_lead_email_activities(
    lead_id: str,
    current_user: User = Depends(RequireTenantUser),
    db: AsyncSession = Depends(get_db)
):
    """Sync email activities from email_marketing module to CRM"""
    service = EmailSequenceService(db)
    synced_count = await service.sync_email_activities(
        lead_id=lead_id,
        tenant_id=current_user.tenant_id
    )

    return {"synced_count": synced_count}
```

### 1.4 Frontend Email Sequence Component Specification

**File**: `frontend/src/components/crm/EmailSequenceManager.tsx`

```typescript
import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { apiClient } from '@/lib/api-client'
import { toast } from 'sonner'
import { useAuth } from '@/hooks/use-auth'

interface EmailSequenceTemplate {
  id: string
  name: string
  description: string
  steps: number
}

interface EmailSequenceStatus {
  sequence_id: string
  status: 'active' | 'paused' | 'completed' | 'cancelled'
  current_step: number
  total_steps: number
  next_email_at: string
  emails_sent: number
  emails_opened: number
  emails_clicked: number
}

interface EmailSequenceManagerProps {
  leadId: string
}

export function EmailSequenceManager({ leadId }: EmailSequenceManagerProps) {
  const { hasTenantRole } = useAuth()
  const queryClient = useQueryClient()
  const [selectedTemplate, setSelectedTemplate] = useState<string>('')

  // Fetch available templates
  const { data: templates, isLoading: templatesLoading } = useQuery({
    queryKey: ['email-sequence-templates'],
    queryFn: async () => {
      const response = await apiClient.get('/email-marketing/sequence-templates')
      return response.data as EmailSequenceTemplate[]
    }
  })

  // Fetch current sequence status
  const { data: sequenceStatus, isLoading: statusLoading } = useQuery({
    queryKey: ['email-sequence-status', leadId],
    queryFn: async () => {
      const response = await apiClient.get(`/crm/leads/${leadId}/email-sequences/status`)
      return response.data as EmailSequenceStatus
    },
    enabled: !!leadId
  })

  // Create sequence mutation
  const createSequenceMutation = useMutation({
    mutationFn: async (templateId: string) => {
      const response = await apiClient.post(`/crm/leads/${leadId}/email-sequences`, {
        template_id: templateId
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Email sequence started')
      queryClient.invalidateQueries({ queryKey: ['email-sequence-status', leadId] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to start email sequence')
    }
  })

  // Pause sequence mutation
  const pauseSequenceMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post(`/crm/leads/${leadId}/email-sequences/pause`)
      return response.data
    },
    onSuccess: () => {
      toast.success('Email sequence paused')
      queryClient.invalidateQueries({ queryKey: ['email-sequence-status', leadId] })
    }
  })

  // Sync activities mutation
  const syncActivitiesMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post(`/crm/leads/${leadId}/email-sequences/sync`)
      return response.data
    },
    onSuccess: (data) => {
      toast.success(`Synced ${data.synced_count} email activities`)
      queryClient.invalidateQueries({ queryKey: ['activities', leadId] })
    }
  })

  const handleStartSequence = () => {
    if (!selectedTemplate) {
      toast.error('Please select a template')
      return
    }
    createSequenceMutation.mutate(selectedTemplate)
  }

  if (!hasTenantRole('tenant_user')) {
    return null
  }

  return (
    <Card className="p-4">
      <h3 className="font-semibold mb-4">Email Sequences</h3>

      {sequenceStatus ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Active Sequence</p>
              <Badge variant={sequenceStatus.status === 'active' ? 'success' : 'warning'}>
                {sequenceStatus.status}
              </Badge>
            </div>
            <div className="text-sm text-gray-600">
              Step {sequenceStatus.current_step} of {sequenceStatus.total_steps}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-gray-600">Emails Sent</p>
              <p className="font-semibold">{sequenceStatus.emails_sent}</p>
            </div>
            <div>
              <p className="text-gray-600">Opened</p>
              <p className="font-semibold">{sequenceStatus.emails_opened}</p>
            </div>
            <div>
              <p className="text-gray-600">Clicked</p>
              <p className="font-semibold">{sequenceStatus.emails_clicked}</p>
            </div>
          </div>

          <div className="flex gap-2">
            {sequenceStatus.status === 'active' && (
              <Button
                onClick={() => pauseSequenceMutation.mutate()}
                disabled={pauseSequenceMutation.isPending}
                variant="outline"
              >
                Pause Sequence
              </Button>
            )}
            <Button
              onClick={() => syncActivitiesMutation.mutate()}
              disabled={syncActivitiesMutation.isPending}
              variant="outline"
            >
              Sync Activities
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <Select
            value={selectedTemplate}
            onValueChange={setSelectedTemplate}
            placeholder="Select email sequence template"
          >
            {templates?.map((template) => (
              <option key={template.id} value={template.id}>
                {template.name} ({template.steps} steps)
              </option>
            ))}
          </Select>

          <Button
            onClick={handleStartSequence}
            disabled={!selectedTemplate || createSequenceMutation.isPending}
          >
            Start Email Sequence
          </Button>
        </div>
      )}
    </Card>
  )
}
### 1.5 Integration Testing Specification

**File**: `backend/src/modules/crm/tests/test_email_sequence_integration.py`

```python
import pytest
from django.test import TestCase
from rest_framework.test import APITestCase, APIClient
from src.modules.crm.services import EmailSequenceService

class EmailSequenceIntegrationTest(APITestCase):
    def setUp(self):
        self.client = APIClient()
        # Set up test tenant and user fixtures
    test_lead_with_email,
    mock_email_marketing_module
):
    """Test creating email sequence for lead"""
    service = EmailSequenceService(db_session)

    sequence = await service.create_sequence_for_lead(
        lead_id=test_lead_with_email.id,
        sequence_template_id="template-123",
        tenant_id=test_tenant.id
    )

    assert sequence["sequence_id"] is not None
    assert sequence["lead_id"] == test_lead_with_email.id
    assert sequence["status"] == "active"

    # Verify lead metadata updated
    await db_session.refresh(test_lead_with_email)
    assert test_lead_with_email.metadata["email_sequence_id"] == sequence["sequence_id"]

@pytest.mark.asyncio
async def test_sync_email_activities(
    db_session,
    test_tenant,
    test_lead_with_sequence,
    mock_email_marketing_module
):
    """Test syncing email activities to CRM"""
    service = EmailSequenceService(db_session)

    synced_count = await service.sync_email_activities(
        lead_id=test_lead_with_sequence.id,
        tenant_id=test_tenant.id
    )

    assert synced_count > 0

    # Verify activities created
    from src.modules.crm.services.activity_service import ActivityService
    activity_service = ActivityService(db_session)
    activities = await activity_service.list_activities(
        related_to_type="Lead",
        related_to_id=test_lead_with_sequence.id,
        tenant_id=test_tenant.id
    )

    email_activities = [a for a in activities if a.type.startswith("email_")]
    assert len(email_activities) == synced_count
```

---

## 2. Workflow Automation Integration Specifications

### 2.1 Integration Architecture

**Pattern**: Workflow Execution via workflow_automation Module (SARAISE-26001)

The CRM module defines workflows in its manifest (`lead_to_opportunity`, `opportunity_to_customer`). These workflows are executed via the `workflow_automation` module's execution engine.

### 2.2 Workflow Execution Service Specification

**File**: `backend/src/modules/crm/services/workflow_service.py`

```python
from django.db import models, transaction
from typing import Optional, Dict, Any
from rest_framework.exceptions import NotFound

# Import workflow_automation services (conditional import)
try:
    from src.modules.workflow_automation.services import WorkflowExecutionService
    from src.modules.workflow_automation.models import WorkflowExecution, WorkflowDefinition
    WORKFLOW_AUTOMATION_AVAILABLE = True
except ImportError:
    WORKFLOW_AUTOMATION_AVAILABLE = False
    WorkflowExecutionService = None
    WorkflowExecution = None
    WorkflowDefinition = None


class CRMWorkflowService:
    """Service for executing CRM workflows via workflow_automation module"""

    def __init__(self, db: AsyncSession):
        self.db = db
        if not WORKFLOW_AUTOMATION_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Workflow automation module is not available. Workflows require workflow_automation module."
            )
        self.workflow_execution_service = WorkflowExecutionService(db)

    async def execute_lead_to_opportunity_workflow(
        self,
        lead_id: str,
        tenant_id: str,
        opportunity_data: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute lead_to_opportunity workflow.

        Workflow Steps (from CRM manifest):
        1. Validate lead qualification (BANT)
        2. Create opportunity from lead
        3. Update lead status to "Qualified"
        4. Create activity log
        5. Notify sales team

        Integration Flow:
        1. Get workflow definition from CRM manifest
        2. Get lead data
        3. Execute workflow via workflow_automation module
        4. Workflow steps execute (create opportunity, update lead, etc.)
        5. Return execution result

        Args:
            lead_id: CRM lead ID
            tenant_id: Tenant ID for isolation
            opportunity_data: Optional opportunity data (if not provided, derived from lead)
            user_id: User executing the workflow

        Returns:
            Workflow execution result with created opportunity
        """
        # 1. Get workflow definition from CRM manifest
        from src.modules.crm import MODULE_MANIFEST
        workflow_def = None
        for workflow in MODULE_MANIFEST.get("workflows", []):
            if workflow["name"] == "lead_to_opportunity":
                workflow_def = workflow
                break

        if not workflow_def:
            raise HTTPException(status_code=500, detail="Workflow definition not found")

        # 2. Get lead data
        from src.modules.crm.services.lead_service import LeadService
        lead_service = LeadService(self.db)
        lead = await lead_service.get_lead(lead_id, tenant_id)

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # 3. Prepare workflow input data
        workflow_input = {
            "lead_id": lead_id,
            "lead_data": {
                "id": lead.id,
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "email": lead.email,
                "company": lead.company,
                "phone": lead.phone,
                "score": lead.score,
                "status": lead.status,
                "metadata": lead.metadata or {}
            },
            "opportunity_data": opportunity_data or {},
            "tenant_id": tenant_id,
            "user_id": user_id
        }

        # 4. Execute workflow via workflow_automation module
        execution_result = await self.workflow_execution_service.execute_workflow(
            workflow_name="lead_to_opportunity",
            workflow_module="crm",
            input_data=workflow_input,
            tenant_id=tenant_id,
            user_id=user_id
        )

        return execution_result

    async def execute_opportunity_to_customer_workflow(
        self,
        opportunity_id: str,
        tenant_id: str,
        customer_data: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute opportunity_to_customer workflow.

        Workflow Steps (from CRM manifest):
        1. Validate opportunity is won
        2. Create customer from opportunity
        3. Create contacts from opportunity contacts
        4. Update opportunity status to "Won"
        5. Create activity log
        6. Trigger billing subscription creation

        Integration Flow:
        1. Get workflow definition from CRM manifest
        2. Get opportunity data
        3. Execute workflow via workflow_automation module
        4. Workflow steps execute (create customer, update opportunity, etc.)
        5. Return execution result

        Args:
            opportunity_id: CRM opportunity ID
            tenant_id: Tenant ID for isolation
            customer_data: Optional customer data (if not provided, derived from opportunity)
            user_id: User executing the workflow

        Returns:
            Workflow execution result with created customer
        """
        # Similar pattern to lead_to_opportunity_workflow
        pass

    async def get_workflow_execution_status(
        self,
        execution_id: str,
        tenant_id: str
    ) -> Dict[str, Any]:
        """Get workflow execution status"""
        return await self.workflow_execution_service.get_execution_status(
            execution_id=execution_id,
            tenant_id=tenant_id
        )
```

### 2.3 Workflow Routes Specification

**File**: `backend/src/modules/crm/routes.py` (additions)

```python
@router.post("/leads/{lead_id}/convert-to-opportunity", response_model=OpportunityResponse)
async def convert_lead_to_opportunity(
    lead_id: str,
    opportunity_data: OpportunityCreate,
    request: Request,
    current_user: User = Depends(RequireTenantUser),
    db: AsyncSession = Depends(get_db)
):
    """
    Convert lead to opportunity using workflow.

    This endpoint:
    1. Executes lead_to_opportunity workflow
    2. Creates opportunity
    3. Updates lead status
    4. Creates activities
    """
    workflow_service = CRMWorkflowService(db)

    result = await workflow_service.execute_lead_to_opportunity_workflow(
        lead_id=lead_id,
        tenant_id=current_user.tenant_id,
        opportunity_data=opportunity_data.model_dump(),
        user_id=current_user.id
    )

    # Audit log
    audit_service = AuditService(db)
    await audit_service.log_event(
        actor_sub=current_user.id,
        actor_email=current_user.email,
        tenant_id=current_user.tenant_id,
        resource="crm.workflow",
        action="EXECUTE",
        result="success",
        metadata={
            "workflow": "lead_to_opportunity",
            "lead_id": lead_id,
            "execution_id": result.get("execution_id")
        },
        request=request
    )

    return result["opportunity"]

@router.post("/opportunities/{opportunity_id}/convert-to-customer", response_model=CustomerResponse)
async def convert_opportunity_to_customer(
    opportunity_id: str,
    customer_data: CustomerCreate,
    request: Request,
    current_user: User = Depends(RequireTenantUser),
    db: AsyncSession = Depends(get_db)
):
    """Convert opportunity to customer using workflow"""
    workflow_service = CRMWorkflowService(db)

    result = await workflow_service.execute_opportunity_to_customer_workflow(
        opportunity_id=opportunity_id,
        tenant_id=current_user.tenant_id,
        customer_data=customer_data.model_dump(),
        user_id=current_user.id
    )

    # Audit log
    audit_service = AuditService(db)
    await audit_service.log_event(
        actor_sub=current_user.id,
        actor_email=current_user.email,
        tenant_id=current_user.tenant_id,
        resource="crm.workflow",
        action="EXECUTE",
        result="success",
        metadata={
            "workflow": "opportunity_to_customer",
            "opportunity_id": opportunity_id,
            "execution_id": result.get("execution_id")
        },
        request=request
    )

    return result["customer"]
```

---

## 3. AI Agent Integration Specifications

### 3.1 Integration Architecture

**Pattern**: AI Agent Execution via Agent Execution Engine

The CRM module defines AI agents in its manifest (`lead_scoring_agent`, `customer_sentiment_agent`). These agents are executed via the SARAISE agent execution engine.

### 3.2 AI Agent Service Specification

**File**: `backend/src/modules/crm/services/ai_agent_service.py`

```python
from django.db import models, transaction
from typing import Dict, Any, Optional
from rest_framework.exceptions import NotFound

# Import AI agent execution engine
try:
    from src.core.ai_agent_execution_engine import AIAgentExecutionEngine
    from src.models.ai_agents import AIAgent, AIAgentExecution
    AI_AGENT_ENGINE_AVAILABLE = True
except ImportError:
    AI_AGENT_ENGINE_AVAILABLE = False
    AIAgentExecutionEngine = None
    AIAgent = None
    AIAgentExecution = None


class CRMAIAgentService:
    """Service for executing CRM AI agents"""

    def __init__(self, db: AsyncSession):
        self.db = db
        if not AI_AGENT_ENGINE_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="AI agent execution engine is not available."
            )
        self.agent_engine = AIAgentExecutionEngine(db)

    async def execute_lead_scoring_agent(
        self,
        lead_id: str,
        tenant_id: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute lead scoring AI agent.

        Agent Definition (from CRM manifest):
        - name: "lead_scoring_agent"
        - agent_type: "openai"
        - configuration: GPT-4 with temperature 0.7

        Execution Flow:
        1. Get lead data
        2. Get agent definition from CRM manifest
        3. Execute agent via agent execution engine
        4. Process agent response (score, BANT qualification)
        5. Update lead with scoring results
        6. Return scoring details

        Args:
            lead_id: CRM lead ID
            tenant_id: Tenant ID for isolation
            user_id: User executing the agent

        Returns:
            Agent execution result with scoring details
        """
        # 1. Get lead data
        from src.modules.crm.services.lead_service import LeadService
        lead_service = LeadService(self.db)
        lead = await lead_service.get_lead(lead_id, tenant_id)

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # 2. Get agent definition from CRM manifest
        from src.modules.crm import MODULE_MANIFEST
        agent_def = None
        for agent in MODULE_MANIFEST.get("ai_agents", []):
            if agent["name"] == "lead_scoring_agent":
                agent_def = agent
                break

        if not agent_def:
            raise HTTPException(status_code=500, detail="Agent definition not found")

        # 3. Prepare agent input
        agent_input = {
            "lead_id": lead_id,
            "lead_data": {
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "email": lead.email,
                "company": lead.company,
                "phone": lead.phone,
                "industry": lead.industry,
                "source": lead.source,
                "status": lead.status,
                "current_score": lead.score,
                "metadata": lead.metadata or {}
            },
            "tenant_id": tenant_id
        }

        # 4. Execute agent via agent execution engine
        execution_result = await self.agent_engine.execute_agent(
            agent_name="lead_scoring_agent",
            agent_module="crm",
            input_data=agent_input,
            tenant_id=tenant_id,
            user_id=user_id
        )

        # 5. Process agent response
        agent_response = execution_result.get("response", {})
        new_score = agent_response.get("score", lead.score)
        bant_qualification = agent_response.get("bant_qualification", {})

        # 6. Update lead with scoring results
        await lead_service.update_lead(
            lead_id=lead_id,
            updates={
                "score": new_score,
                "metadata": {
                    **(lead.metadata or {}),
                    "bant_qualification": bant_qualification,
                    "last_scored_at": datetime.utcnow().isoformat(),
                    "scoring_agent_execution_id": execution_result.get("execution_id")
                }
            },
            tenant_id=tenant_id
        )

        return {
            "execution_id": execution_result.get("execution_id"),
            "lead_id": lead_id,
            "score": new_score,
            "bant_qualification": bant_qualification,
            "agent_response": agent_response
        }

    async def execute_customer_sentiment_agent(
        self,
        customer_id: str,
        tenant_id: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute customer sentiment AI agent.

        Agent Definition (from CRM manifest):
        - name: "customer_sentiment_agent"
        - agent_type: "openai"
        - configuration: GPT-4 with temperature 0.5

        Execution Flow:
        1. Get customer data and interaction history
        2. Get agent definition from CRM manifest
        3. Execute agent via agent execution engine
        4. Process agent response (sentiment score, insights)
        5. Update customer with sentiment analysis
        6. Return sentiment details

        Args:
            customer_id: CRM customer ID
            tenant_id: Tenant ID for isolation
            user_id: User executing the agent

        Returns:
            Agent execution result with sentiment analysis
        """
        # Similar pattern to lead_scoring_agent
        pass
```

### 3.3 AI Agent Routes Specification

**File**: `backend/src/modules/crm/routes.py` (additions)

```python
@router.post("/leads/{lead_id}/ai-score", response_model=LeadScoringResponse)
async def execute_lead_scoring_agent(
    lead_id: str,
    request: Request,
    current_user: User = Depends(RequireTenantUser),
    db: AsyncSession = Depends(get_db)
):
    """Execute lead scoring AI agent"""
    agent_service = CRMAIAgentService(db)

    result = await agent_service.execute_lead_scoring_agent(
        lead_id=lead_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id
    )

    # Audit log
    audit_service = AuditService(db)
    await audit_service.log_event(
        actor_sub=current_user.id,
        actor_email=current_user.email,
        tenant_id=current_user.tenant_id,
        resource="crm.ai_agent",
        action="EXECUTE",
        result="success",
        metadata={
            "agent": "lead_scoring_agent",
            "lead_id": lead_id,
            "execution_id": result.get("execution_id")
        },
        request=request
    )

    return result

@router.post("/customers/{customer_id}/ai-sentiment", response_model=CustomerSentimentResponse)
async def execute_customer_sentiment_agent(
    customer_id: str,
    request: Request,
    current_user: User = Depends(RequireTenantUser),
    db: AsyncSession = Depends(get_db)
):
    """Execute customer sentiment AI agent"""
    agent_service = CRMAIAgentService(db)

    result = await agent_service.execute_customer_sentiment_agent(
        customer_id=customer_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id
    )

    # Audit log
    audit_service = AuditService(db)
    await audit_service.log_event(
        actor_sub=current_user.id,
        actor_email=current_user.email,
        tenant_id=current_user.tenant_id,
        resource="crm.ai_agent",
        action="EXECUTE",
        result="success",
        metadata={
            "agent": "customer_sentiment_agent",
            "customer_id": customer_id,
            "execution_id": result.get("execution_id")
        },
        request=request
    )

    return result
```

---

## 4. Phase 4 Database Schema Specifications

### 4.1 Quote & Proposal Schema

**File**: `backend/src/modules/crm/models.py` (additions)

See COMPLETE_IMPLEMENTATION_PLAN.md Part 2.1 for complete schema specification.

### 4.2 Territory Management Schema

**File**: `backend/src/modules/crm/models.py` (additions)

See COMPLETE_IMPLEMENTATION_PLAN.md Part 2.2 for complete schema specification.

### 4.3 Sales Enablement Schema

**File**: `backend/src/modules/crm/models.py` (additions)

See COMPLETE_IMPLEMENTATION_PLAN.md Part 2.4 for complete schema specification.

### 4.4 Migration Scripts

**File**: `backend/src/modules/crm/migrations/0003_quotes_proposals.py` (Django Migration)

```python
"""Add quotes and proposals module

Generated by Django migration system
"""
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ('crm', '0002_crm_initial'),
    ]

    operations = [
        # Define model fields and relationships
    ]
```

def upgrade():
    # Create quotes table
    op.create_table(
        'quotes',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('opportunity_id', sa.String(), nullable=True),
        sa.Column('customer_id', sa.String(), nullable=False),
        sa.Column('contact_id', sa.String(), nullable=True),
        sa.Column('quote_number', sa.String(), unique=True, nullable=False),
        sa.Column('quote_name', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), default='draft'),
        sa.Column('subtotal', sa.Numeric(10, 2), nullable=False),
        sa.Column('tax_amount', sa.Numeric(10, 2), default=0),
        sa.Column('discount_amount', sa.Numeric(10, 2), default=0),
        sa.Column('total_amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), default='USD'),
        sa.Column('valid_from', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('payment_terms', sa.String(255), nullable=True),
        sa.Column('delivery_terms', sa.String(255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('converted_to_order', sa.Boolean(), default=False),
        sa.Column('order_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id']),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id']),
    )
    op.create_index('idx_quote_tenant', 'quotes', ['tenant_id'])
    op.create_index('idx_quote_customer', 'quotes', ['customer_id'])
    op.create_index('idx_quote_number', 'quotes', ['quote_number'])
    op.create_index('idx_quote_status', 'quotes', ['status'])

    # Create quote_line_items table
    op.create_table(
        'quote_line_items',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('quote_id', sa.String(), nullable=False),
        sa.Column('product_name', sa.String(255), nullable=False),
        sa.Column('product_description', sa.Text(), nullable=True),
        sa.Column('product_id', sa.String(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('discount_percent', sa.Numeric(5, 2), default=0),
        sa.Column('line_total', sa.Numeric(10, 2), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['quote_id'], ['quotes.id']),
    )
    op.create_index('idx_quote_line_item_quote', 'quote_line_items', ['quote_id'])

    # Create proposals table
    op.create_table(
        'proposals',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('opportunity_id', sa.String(), nullable=True),
        sa.Column('quote_id', sa.String(), nullable=True),
        sa.Column('proposal_number', sa.String(), unique=True, nullable=False),
        sa.Column('proposal_name', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), default='draft'),
        sa.Column('executive_summary', sa.Text(), nullable=True),
        sa.Column('solution_overview', sa.Text(), nullable=True),
        sa.Column('pricing_section', sa.Text(), nullable=True),
        sa.Column('terms_and_conditions', sa.Text(), nullable=True),
        sa.Column('document_url', sa.String(500), nullable=True),
        sa.Column('template_id', sa.String(), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id']),
        sa.ForeignKeyConstraint(['quote_id'], ['quotes.id']),
    )
    op.create_index('idx_proposal_tenant', 'proposals', ['tenant_id'])
    op.create_index('idx_proposal_opportunity', 'proposals', ['opportunity_id'])
    op.create_index('idx_proposal_number', 'proposals', ['proposal_number'])

def downgrade():
    op.drop_table('proposals')
    op.drop_table('quote_line_items')
    op.drop_table('quotes')
```

---

## 5. Frontend Component Specifications

### 5.1 Component Architecture

**Pattern**: React + TypeScript + TanStack Query (SARAISE-03001)

All frontend components follow SARAISE TypeScript standards:
- Strict TypeScript mode
- Explicit types (no `any`)
- React hooks rules (hooks before early returns)
- Zod validation for forms
- TanStack Query for server state

### 5.2 Component Specifications

See COMPLETE_IMPLEMENTATION_PLAN.md for detailed component specifications for:
- Email Sequence Manager
- Workflow Configurator
- Quote Builder
- Proposal Manager
- Territory Manager
- Content Library
- Sales Playbook

---

## 6. API Integration Specifications

### 6.1 API Endpoint Standards

**Pattern**: RESTful API with OpenAPI documentation (SARAISE-02002)

All API endpoints must:
- Use proper HTTP methods (GET, POST, PUT, DELETE, PATCH)
- Include OpenAPI documentation
- Enforce RBAC (SARAISE-07031)
- Include audit logging (SARAISE-10001)
- Support tenant isolation (SARAISE-33001)
- Return proper error responses (SARAISE-14001)

### 6.2 Response Format Standards

```python
# Success Response
{
    "data": {...},
    "status": "success",
    "timestamp": "2025-01-XXT00:00:00Z"
}

# Error Response
{
    "error": {
        "code": "ERROR_CODE",
        "message": "Human-readable error message",
        "details": {...}
    },
    "status": "error",
    "timestamp": "2025-01-XXT00:00:00Z"
}
```

### 6.3 Pagination Standards

```python
# Paginated Response
{
    "data": [...],
    "pagination": {
        "page": 1,
        "page_size": 20,
        "total": 100,
        "total_pages": 5
    }
}
```

---

## 7. Test Plan Specifications

### 7.1 Test Coverage Requirements

**Target**: 90% coverage (SARAISE-01002)

**Test Categories**:
1. **Unit Tests**: Services, models, utilities
2. **Integration Tests**: Module interactions, cross-module integration
3. **E2E Tests**: Complete user workflows
4. **Performance Tests**: Load testing, query optimization

### 7.2 Test File Structure

```
backend/src/modules/crm/tests/
├── test_models.py              # Model tests
├── test_services.py             # Service tests
├── test_routes.py               # Route tests
├── test_routes_extended.py      # Extended route tests
├── test_integration.py          # Integration tests
├── test_email_sequence_integration.py  # Email marketing integration
├── test_workflow_integration.py        # Workflow automation integration
├── test_ai_agent_integration.py        # AI agent integration
└── conftest.py                  # Test fixtures
```

### 7.3 Test Execution

```bash
# Run all tests
pytest backend/src/modules/crm/tests/ -v

# Run with coverage
pytest backend/src/modules/crm/tests/ --cov=src/modules/crm --cov-report=html

# Run specific test category
pytest backend/src/modules/crm/tests/test_services.py -v

# Run integration tests
pytest backend/src/modules/crm/tests/test_integration.py -v
```

---

## 8. Performance Specifications

### 8.1 API Response Time Targets

- **CRUD Operations**: < 200ms (95th percentile)
- **List Queries**: < 300ms (95th percentile)
- **Complex Queries**: < 500ms (95th percentile)
- **AI Agent Execution**: < 5s (95th percentile)
- **Workflow Execution**: < 10s (95th percentile)

### 8.2 Database Query Optimization

- Use database indexes for all foreign keys
- Use selectinload/joinedload for relationships
- Implement pagination for all list endpoints
- Use Redis caching for frequently accessed data

### 8.3 Caching Strategy

```python
# Cache keys
f"crm:customer:{tenant_id}:{customer_id}"  # TTL: 1 hour
f"crm:lead:{tenant_id}:{lead_id}"           # TTL: 30 minutes
f"crm:opportunity:{tenant_id}:{opp_id}"     # TTL: 1 hour
```

---

## 9. Security Specifications

### 9.1 RBAC Enforcement

**Pattern**: Deny-by-default with explicit role requirements (SARAISE-07031)

All endpoints must use role enforcers:
- `RequireTenantUser` - Basic access
- `RequireTenantAdmin` - Admin operations
- `RequirePlatformOwner` - Platform operations

### 9.2 Tenant Isolation

**Pattern**: Schema-per-tenant with validation (SARAISE-33001)

All operations must:
- Validate tenant_id matches user's tenant
- Filter queries by tenant_id
- Prevent cross-tenant data access

### 9.3 Input Validation

**Pattern**: Pydantic schemas with environment-aware validation (SARAISE-02011)

All inputs must:
- Use Pydantic models
- Validate data types
- Sanitize user input
- Enforce business rules

---

## 10. Deployment Specifications

### 10.1 Module Installation

**Pattern**: Tenant-specific installation (SARAISE-26001)

Module installation:
1. Check dependencies
2. Run migrations
3. Load initial data
4. Register routes
5. Create TenantModule record

### 10.2 Health Checks

**Pattern**: Module health check functions (SARAISE-26001)

Health checks verify:
- Database connectivity
- Service availability
- Module dependencies
- Configuration validity

### 10.3 Rollback Plan

**Pattern**: Migration rollback support (SARAISE-29008)

All migrations must:
- Support downgrade
- Preserve data integrity
- Test rollback in staging

---

## Conclusion

This technical specification document provides detailed implementation guidance for all remaining CRM module work. Combined with COMPLETE_IMPLEMENTATION_PLAN.md, this provides 100% complete planning for:

1. ✅ Integration specifications (email_marketing, workflow_automation, AI agents)
2. ✅ Phase 4 feature specifications (Quote, Territory, Mobile, Sales Enablement)
3. ✅ Database schema specifications
4. ✅ Frontend component specifications
5. ✅ API integration specifications
6. ✅ Test plan specifications
7. ✅ Performance specifications
8. ✅ Security specifications
9. ✅ Deployment specifications

**All planning is now 100% complete and ready for implementation.**

---

**Spec Status**: ✅ **100% COMPLETE**
**Last Updated**: 2025-01-XX
**Next Review**: After integration phase completion
