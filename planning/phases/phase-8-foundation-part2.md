# Phase 8: Foundation Modules Part 2 — Platform Services

**Duration:** 5 weeks (Weeks 6-10)  
**Modules:** Workflow Automation, Metadata Modeling, Document Management, Integration Platform  
**Status:** 🟡 PENDING (Blocked on Phase 7)  
**Prerequisites:** Phase 7 complete (Platform, Tenant, Security operational)

---

## Phase Objectives

Implement 4 Platform Service modules that enable workflow automation, custom data modeling, document management, and external integrations.

### Success Criteria
- [ ] 4 modules operational (backend + frontend + tests)
- [ ] ≥90% test coverage per module
- [ ] All pre-commit hooks passing
- [ ] Integration with Phase 7 modules verified

---

## Week 6-7: Workflow Automation Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `workflow_automation` |
| Type | Foundation |
| Priority | P1 |
| Dependencies | Security & Access Control |
| Spec Location | `docs/modules/01-foundation/workflow-automation/` |
| Timeline | 7-10 days |

### Key Entities (from spec)

```python
# Core workflow entities
- Workflow (name, description, trigger_type, status, tenant_id)
- WorkflowStep (workflow_id, step_type, config, order)
- WorkflowTransition (workflow_id, from_step, to_step, condition)
- WorkflowInstance (workflow_id, current_step, state, data)
- WorkflowTask (instance_id, assignee_id, status, due_date)
- ApprovalRequest (instance_id, approver_id, status, decision)
```

### API Endpoints

```
# Workflow definitions
GET/POST /api/v1/workflows/
GET/PUT/DELETE /api/v1/workflows/{id}/
POST /api/v1/workflows/{id}/publish/
POST /api/v1/workflows/{id}/archive/

# Workflow instances
POST /api/v1/workflows/{id}/start/
GET /api/v1/workflow-instances/
GET /api/v1/workflow-instances/{id}/
POST /api/v1/workflow-instances/{id}/transition/

# Tasks & Approvals
GET /api/v1/workflow-tasks/
POST /api/v1/workflow-tasks/{id}/complete/
GET /api/v1/approvals/
POST /api/v1/approvals/{id}/approve/
POST /api/v1/approvals/{id}/reject/
```

### Day-by-Day Execution

**Day 1: Specification Review**
```bash
# Read spec
cat docs/modules/01-foundation/workflow-automation/README.md
cat docs/modules/01-foundation/workflow-automation/API.md

# Extract:
# 1. Data models (entities, fields, relationships)
# 2. Business rules (state machines, transitions)
# 3. API contracts
# 4. Test scenarios
```

**Day 2-4: Backend Implementation**
```bash
# Create module structure
cd backend/src/modules
mkdir -p workflow_automation/{migrations,tests}
touch workflow_automation/{__init__.py,manifest.yaml,models.py,serializers.py,api.py,urls.py,services.py}
touch workflow_automation/tests/{__init__.py,test_api.py,test_services.py,test_isolation.py}

# Implement following pattern from ai_agent_management:
# 1. models.py - All entities with tenant_id
# 2. serializers.py - DRF serializers
# 3. api.py - ViewSets with tenant filtering
# 4. urls.py - Router configuration
# 5. services.py - State machine logic
```

**Key Implementation: Workflow State Machine**
```python
# backend/src/modules/workflow_automation/services.py

class WorkflowEngine:
    """State machine for workflow execution."""

    def start_workflow(
        self,
        workflow_id: uuid.UUID,
        tenant_id: uuid.UUID,
        initial_data: dict
    ) -> WorkflowInstance:
        """Start a new workflow instance."""
        workflow = Workflow.objects.get(id=workflow_id, tenant_id=tenant_id)

        if workflow.status != 'published':
            raise ValueError("Workflow must be published to start")

        first_step = workflow.steps.order_by('order').first()

        instance = WorkflowInstance.objects.create(
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            current_step=first_step,
            state='running',
            data=initial_data
        )

        self._execute_step(instance, first_step)
        return instance

    def transition(
        self,
        instance_id: uuid.UUID,
        tenant_id: uuid.UUID,
        transition_id: uuid.UUID
    ) -> WorkflowInstance:
        """Transition workflow to next step."""
        instance = WorkflowInstance.objects.get(
            id=instance_id,
            tenant_id=tenant_id  # TENANT ISOLATION
        )

        transition = WorkflowTransition.objects.get(
            id=transition_id,
            workflow_id=instance.workflow_id
        )

        # Validate transition
        if transition.from_step_id != instance.current_step_id:
            raise ValueError("Invalid transition from current step")

        # Check condition
        if not self._evaluate_condition(transition.condition, instance.data):
            raise ValueError("Transition condition not met")

        # Execute transition
        instance.current_step = transition.to_step
        instance.save()

        self._execute_step(instance, transition.to_step)
        return instance
```

**Day 4-5: Tests**
```python
# backend/src/modules/workflow_automation/tests/test_isolation.py

class WorkflowIsolationTestCase(TestCase):
    """Tenant isolation tests for workflows."""

    def test_user_cannot_start_other_tenant_workflow(self):
        """User cannot start workflow from another tenant."""
        other_workflow = Workflow.objects.create(
            tenant_id=self.other_tenant_id,
            name='Other Workflow',
            status='published'
        )

        self.client.force_authenticate(user=self.user_a)
        response = self.client.post(
            f'/api/v1/workflows/{other_workflow.id}/start/',
            {'data': {}}
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_cannot_transition_other_tenant_instance(self):
        """User cannot transition workflow instance from another tenant."""
        # ... similar pattern
```

**Day 5-7: Frontend Implementation**
```typescript
// frontend/src/modules/workflow_automation/types/index.ts

export interface Workflow {
  id: string;
  tenant_id: string;
  name: string;
  description: string;
  trigger_type: 'manual' | 'scheduled' | 'event';
  status: 'draft' | 'published' | 'archived';
  steps: WorkflowStep[];
  created_at: string;
  updated_at: string;
}

export interface WorkflowStep {
  id: string;
  workflow_id: string;
  step_type: 'action' | 'decision' | 'approval' | 'notification';
  name: string;
  config: Record<string, unknown>;
  order: number;
}

export interface WorkflowInstance {
  id: string;
  workflow_id: string;
  tenant_id: string;
  current_step_id: string;
  state: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  data: Record<string, unknown>;
  started_at: string;
  completed_at: string | null;
}
```

### Validation Checkpoint

```bash
# After Week 6-7 completion
cd backend
pytest src/modules/workflow_automation/tests/ -v --cov --cov-fail-under=90

cd ../frontend
npx tsc --noEmit
npx eslint src/modules/workflow_automation --max-warnings 0
```

---

## Week 7-8: Metadata Modeling Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `metadata_modeling` |
| Type | Foundation |
| Priority | P1 |
| Dependencies | Security & Access Control |
| Spec Location | `docs/modules/01-foundation/metadata-modeling/` |
| Timeline | 5-7 days |

### Key Entities

```python
# Dynamic schema entities
- EntityDefinition (name, display_name, description, tenant_id)
- FieldDefinition (entity_id, name, field_type, constraints, tenant_id)
- RelationshipDefinition (source_entity, target_entity, type, tenant_id)
- DynamicResource (entity_definition_id, data, tenant_id)
```

### Key Implementation: Dynamic Fields

```python
# backend/src/modules/metadata_modeling/models.py

class FieldDefinition(models.Model):
    """Defines a custom field for an entity."""

    FIELD_TYPES = [
        ('string', 'String'),
        ('text', 'Text'),
        ('integer', 'Integer'),
        ('decimal', 'Decimal'),
        ('boolean', 'Boolean'),
        ('date', 'Date'),
        ('datetime', 'DateTime'),
        ('select', 'Select'),
        ('multi_select', 'Multi-Select'),
        ('reference', 'Reference'),
        ('file', 'File'),
        ('json', 'JSON'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tenant_id = models.UUIDField(db_index=True)
    entity_definition = models.ForeignKey(
        EntityDefinition,
        on_delete=models.CASCADE,
        related_name='fields'
    )

    name = models.CharField(max_length=100)
    display_name = models.CharField(max_length=255)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES)
    is_required = models.BooleanField(default=False)
    is_unique = models.BooleanField(default=False)
    default_value = models.JSONField(null=True, blank=True)
    constraints = models.JSONField(default=dict)  # min, max, regex, options
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'metadata_field_definitions'
        unique_together = [['tenant_id', 'entity_definition', 'name']]


class DynamicResource(models.Model):
    """Stores instances of dynamic entities."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tenant_id = models.UUIDField(db_index=True)
    entity_definition = models.ForeignKey(
        EntityDefinition,
        on_delete=models.CASCADE
    )
    data = models.JSONField(default=dict)  # Flexible data storage

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.UUIDField(null=True)

    class Meta:
        db_table = 'metadata_dynamic_resources'
        indexes = [
            models.Index(fields=['tenant_id', 'entity_definition']),
        ]
```

### Day-by-Day Execution

- **Day 1**: Read spec, extract schema definitions
- **Day 2-3**: Backend models, dynamic field validation
- **Day 3-4**: Tests with complex field types
- **Day 4-5**: Frontend form builder components

---

## Week 8-9: Document Management (DMS) Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `document_management` |
| Type | Foundation |
| Priority | P1 |
| Dependencies | Security, Metadata Modeling |
| Spec Location | `docs/modules/01-foundation/dms/` |
| Timeline | 5-7 days |

### Key Entities

```python
# Document storage entities
- Folder (name, parent_id, path, tenant_id)
- Document (name, folder_id, file_path, mime_type, size, tenant_id)
- DocumentVersion (document_id, version_number, file_path, created_by)
- DocumentPermission (document_id, principal_type, principal_id, permission)
- DocumentShare (document_id, share_token, expires_at, permissions)
```

### API Endpoints

```
# Folders
GET/POST /api/v1/dms/folders/
GET/PUT/DELETE /api/v1/dms/folders/{id}/
POST /api/v1/dms/folders/{id}/move/

# Documents
GET/POST /api/v1/dms/documents/
GET/PUT/DELETE /api/v1/dms/documents/{id}/
POST /api/v1/dms/documents/{id}/upload/
GET /api/v1/dms/documents/{id}/download/
GET /api/v1/dms/documents/{id}/versions/
POST /api/v1/dms/documents/{id}/share/
```

### Key Implementation: File Storage Service

```python
# backend/src/modules/document_management/services.py

import os
import hashlib
from django.conf import settings
from django.core.files.storage import default_storage


class DocumentStorageService:
    """Handles file storage with tenant isolation."""

    def upload_document(
        self,
        tenant_id: str,
        folder_id: str,
        file,
        filename: str,
        user_id: str
    ) -> Document:
        """Upload document with tenant isolation."""

        # Generate tenant-isolated path
        file_hash = hashlib.sha256(file.read()).hexdigest()
        file.seek(0)

        storage_path = f"tenants/{tenant_id}/documents/{file_hash[:2]}/{file_hash}"

        # Save file
        saved_path = default_storage.save(storage_path, file)

        # Create document record
        document = Document.objects.create(
            tenant_id=tenant_id,
            folder_id=folder_id,
            name=filename,
            file_path=saved_path,
            mime_type=file.content_type,
            size=file.size,
            checksum=file_hash,
            created_by=user_id
        )

        # Create initial version
        DocumentVersion.objects.create(
            document=document,
            version_number=1,
            file_path=saved_path,
            created_by=user_id
        )

        return document

    def download_document(
        self,
        tenant_id: str,
        document_id: str
    ) -> tuple:
        """Download document with tenant verification."""

        document = Document.objects.get(
            id=document_id,
            tenant_id=tenant_id  # TENANT ISOLATION
        )

        file = default_storage.open(document.file_path)
        return file, document.name, document.mime_type
```

---

## Week 9-10: Integration Platform Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `integration_platform` |
| Type | Foundation |
| Priority | P1 |
| Dependencies | Security, Workflow |
| Spec Location | `docs/modules/01-foundation/integration-platform/` |
| Timeline | 5-7 days |

### Key Entities

```python
# Integration entities
- Integration (name, type, config, status, tenant_id)
- IntegrationCredential (integration_id, credential_type, encrypted_value)
- Webhook (name, url, events, secret, tenant_id)
- WebhookDelivery (webhook_id, event, payload, status, response)
- Connector (name, type, schema, config)
- DataMapping (integration_id, source_field, target_field, transform)
```

### API Endpoints

```
# Integrations
GET/POST /api/v1/integrations/
GET/PUT/DELETE /api/v1/integrations/{id}/
POST /api/v1/integrations/{id}/test/
POST /api/v1/integrations/{id}/sync/

# Webhooks
GET/POST /api/v1/webhooks/
GET/PUT/DELETE /api/v1/webhooks/{id}/
POST /api/v1/webhooks/receive/{webhook_id}/

# Connectors
GET /api/v1/connectors/
GET /api/v1/connectors/{id}/schema/
```

### Key Implementation: Webhook Handler

```python
# backend/src/modules/integration_platform/services.py

import hmac
import hashlib
import json
import httpx
from django.utils import timezone


class WebhookService:
    """Handles webhook delivery and verification."""

    def deliver_webhook(
        self,
        webhook: Webhook,
        event: str,
        payload: dict
    ) -> WebhookDelivery:
        """Deliver webhook with retry and logging."""

        # Sign payload
        signature = self._sign_payload(webhook.secret, payload)

        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Signature': signature,
            'X-Webhook-Event': event,
            'X-Tenant-ID': str(webhook.tenant_id),
        }

        delivery = WebhookDelivery.objects.create(
            webhook=webhook,
            event=event,
            payload=payload,
            status='pending'
        )

        try:
            response = httpx.post(
                webhook.url,
                json=payload,
                headers=headers,
                timeout=30
            )

            delivery.status = 'delivered' if response.is_success else 'failed'
            delivery.response_code = response.status_code
            delivery.response_body = response.text[:10000]
            delivery.delivered_at = timezone.now()

        except Exception as e:
            delivery.status = 'failed'
            delivery.error_message = str(e)

        delivery.save()
        return delivery

    def _sign_payload(self, secret: str, payload: dict) -> str:
        """Sign payload with HMAC-SHA256."""
        message = json.dumps(payload, sort_keys=True)
        return hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
```

---

## Phase Completion Criteria

### Mandatory Checkpoints

- [ ] 4 modules operational (backend + frontend)
- [ ] ≥90% test coverage per module
- [ ] All pre-commit hooks passing
- [ ] Tenant isolation tests passing
- [ ] Integration with Phase 7 modules verified
- [ ] Cross-module workflows tested

### Final Validation

```bash
# Phase 8 completion validation
cd /Users/raghunathchava/Code/saraise

# 1. All pre-commit hooks
pre-commit run --all-files

# 2. Backend tests
cd backend
pytest src/modules/workflow_automation/tests/ -v --cov --cov-fail-under=90
pytest src/modules/metadata_modeling/tests/ -v --cov --cov-fail-under=90
pytest src/modules/document_management/tests/ -v --cov --cov-fail-under=90
pytest src/modules/integration_platform/tests/ -v --cov --cov-fail-under=90

# 3. Frontend
cd ../frontend
npx tsc --noEmit
npx eslint src/modules --max-warnings 0
npm test

# 4. Integration test - workflow using DMS
pytest tests/integration/test_workflow_dms.py -v
```

---

## Document Status

**Status:** PENDING (Blocked on Phase 7)  
**Last Updated:** January 5, 2026  
**Next Phase:** Phase 9 (Billing, Migration, AI Config, Localization)

---

