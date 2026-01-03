<!-- SPDX-License-Identifier: Apache-2.0 -->
# Email Marketing - User Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-02

---

## Overview

This guide provides instructions for using the Email Marketing module.

## Getting Started

<!-- TODO: Add getting started instructions -->

## Features

<!-- TODO: Add feature documentation -->

## Usage

<!-- TODO: Add usage instructions -->

## Customization

<!-- TODO: Add customization options -->

## Integrations

<!-- TODO: Add integration information -->


## Customization

<!-- SPDX-License-Identifier: Apache-2.0 -->
# Email Marketing Module Customization Guide

**Module**: Email Marketing
**Category**: Communication & Marketing
**Version**: 1.0.0

---

## Overview

This guide documents all customization points available in the Email Marketing module. Use these customization capabilities to extend email campaign management, integrate with external email providers, implement custom automation workflows, and add business logic without modifying core code.

The Email Marketing module provides email campaign creation, sending, automation, analytics, and integration with AI agents for optimization.

---

## Customization Points

### 1. EmailCampaign Model

**Description**: Email marketing campaign

**Available Hooks**:
- `before_insert` - Before creating a campaign
- `after_insert` - After a campaign is created
- `before_update` - Before updating a campaign
- `after_update` - After a campaign is updated
- `before_delete` - Before deleting a campaign

**Use Cases**:
- Auto-optimize send times using AI
- Apply A/B testing rules
- Validate campaign data
- Trigger campaign workflows
- Update campaign status
- Generate campaign reports

**Example Server Script - Campaign Send Time Optimization**:
```python
# Server script: Auto-optimize email send times
# EventBusEvent: before_insert
# Resource: EmailCampaign

# Use AI agent to optimize send time
if not doc.get('scheduled_send_time'):
    # Get recipient timezone data (would query from contact/segment data)
    recipient_timezones = context.query("Contact", filters={
        "segment_id": doc.get('segment_id')
    }, fields=["timezone"])

    # Call AI agent for send time optimization
    optimization_result = context.call_ai_agent(
        "email_send_time_optimizer",
        {
            "campaign_type": doc.get('campaign_type'),
            "recipient_timezones": recipient_timezones,
            "target_audience": doc.get('target_audience')
        }
    )

    if optimization_result and 'optimal_send_time' in optimization_result:
        doc['scheduled_send_time'] = optimization_result['optimal_send_time']
        doc['send_time_optimized'] = True
        context.log(f"Campaign {doc.get('id')} send time optimized to {doc['scheduled_send_time']}", 'info')

result = doc
```

**Example Server Script - Subject Line Generation**:
```python
# Server script: Auto-generate subject lines using AI
# EventBusEvent: before_insert
# Resource: EmailCampaign

# Generate subject line if not provided
if not doc.get('subject_line'):
    # Call AI agent for subject line generation
    subject_result = context.call_ai_agent(
        "email_subject_line_generator",
        {
            "campaign_content": doc.get('content_preview', ''),
            "campaign_type": doc.get('campaign_type'),
            "target_audience": doc.get('target_audience'),
            "tone": doc.get('tone', 'professional')
        }
    )

    if subject_result and 'subject_line' in subject_result:
        doc['subject_line'] = subject_result['subject_line']
        doc['subject_line_generated'] = True
        context.log(f"Campaign {doc.get('id')} subject line generated: {doc['subject_line']}", 'info')

result = doc
```

---

### 2. EmailMessage Resource

**Description**: Individual email message/recipient

**Available Hooks**:
- `before_insert` - Before creating email message
- `after_insert` - After email message is created
- `before_update` - Before updating email message
- `after_update` - After email message is updated

**Use Cases**:
- Personalize email content
- Apply dynamic content rules
- Track email delivery status
- Handle bounces and unsubscribes
- Update recipient engagement

**Example Server Script - Content Personalization**:
```python
# Server script: Personalize email content
# EventBusEvent: before_insert
# Resource: EmailMessage

# Personalize email content for recipient
if doc.get('recipient_id') and doc.get('campaign_id'):
    # Get recipient data
    recipient = context.query("Contact", filters={"id": doc['recipient_id']}, single=True)

    if recipient:
        # Get campaign template
        campaign = context.query("EmailCampaign", filters={"id": doc['campaign_id']}, single=True)

        if campaign and campaign.get('content_template'):
            # Call AI agent for content personalization
            personalized_content = context.call_ai_agent(
                "email_content_personalizer",
                {
                    "template": campaign['content_template'],
                    "recipient_name": recipient.get('name'),
                    "recipient_segment": recipient.get('segment'),
                    "recipient_history": recipient.get('email_history', []),
                    "campaign_type": campaign.get('campaign_type')
                }
            )

            if personalized_content and 'personalized_content' in personalized_content:
                doc['content'] = personalized_content['personalized_content']
                doc['personalized'] = True
                context.log(f"Email {doc.get('id')} personalized for {recipient.get('name')}", 'info')

result = doc
```

---

### 3. EmailSendLog Resource

**Description**: Email send tracking and analytics

**Available Hooks**:
- `before_insert` - Before creating send log
- `after_insert` - After send log is created
- `after_update` - After send log is updated (for status updates)

**Use Cases**:
- Track email delivery
- Handle bounce processing
- Update engagement metrics
- Trigger follow-up actions
- Generate analytics reports

**Example Server Script - Bounce Handling**:
```python
# Server script: Handle email bounces
# EventBusEvent: after_update
# Resource: EmailSendLog

# Process bounces and update recipient status
if doc.get('status') == 'bounced':
    bounce_type = doc.get('bounce_type', 'hard')  # hard or soft

    if bounce_type == 'hard':
        # Hard bounce - mark recipient as invalid
        if doc.get('recipient_id'):
            recipient = context.query("Contact", filters={"id": doc['recipient_id']}, single=True)
            if recipient:
                recipient['email_status'] = 'invalid'
                recipient['bounced_at'] = context.utils.now()
                context.save(recipient)
                context.log(f"Recipient {doc['recipient_id']} marked as invalid due to hard bounce", 'warning')

    elif bounce_type == 'soft':
        # Soft bounce - increment bounce count
        if doc.get('recipient_id'):
            recipient = context.query("Contact", filters={"id": doc['recipient_id']}, single=True)
            if recipient:
                recipient['soft_bounce_count'] = recipient.get('soft_bounce_count', 0) + 1

                # Mark as invalid after 3 soft bounces
                if recipient['soft_bounce_count'] >= 3:
                    recipient['email_status'] = 'invalid'
                    context.log(f"Recipient {doc['recipient_id']} marked as invalid after 3 soft bounces", 'warning')

                context.save(recipient)

    # Update campaign bounce metrics
    if doc.get('campaign_id'):
        campaign = context.query("EmailCampaign", filters={"id": doc['campaign_id']}, single=True)
        if campaign:
            campaign['bounce_count'] = campaign.get('bounce_count', 0) + 1
            campaign['bounce_rate'] = (campaign['bounce_count'] / campaign.get('sent_count', 1)) * 100
            context.save(campaign)

result = doc
```

---

## Custom API Endpoints

The Email Marketing module supports custom API endpoints using the `@whitelist` decorator. These endpoints are automatically exposed as DRF routes and can be called from frontend components, external systems, or other modules.

### Using the @whitelist Decorator

The `@whitelist` decorator from `src.core.api.decorators` allows you to expose Python functions as API endpoints. Endpoints are automatically registered at `/api/method/<module_path>.<function_name>`.

**Key Features:**
- Automatic route registration
- Parameter validation via DRF serializers
- Authentication handling (optional guest access)
- Support for async functions
- Multiple HTTP methods (POST, GET, PUT, DELETE)

### Example: Email Provider Integration Endpoint

```python
# Custom API endpoint for email provider integration
# File: backend/src/modules/email_marketing/views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from src.core.session_manager import get_current_user_from_session
from src.models.base import User

@api_view(['POST'])
@permission_classes([IsAuthenticated])
async def send_email_via_provider(
    provider_name: str,
    to_email: str,
    subject: str,
    body_html: str,
    body_text: Optional[str] = None,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
    tenant_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_session)
) -> Dict[str, Any]:
    """Send email via configured email service provider

    Available as: POST /api/method/email_marketing.api.send_email_via_provider

    Args:
        provider_name: Name of the email provider (sendgrid, ses, smtp)
        to_email: Recipient email address
        subject: Email subject line
        body_html: HTML email body
        body_text: Plain text email body (optional)
        from_email: Sender email address (optional, uses provider default)
        from_name: Sender name (optional)
        tenant_id: Tenant ID (optional, uses current user's tenant)

    Returns:
        Dict with send status and message ID
    """
    # Use current user's tenant if not provided
    if not tenant_id:
        tenant_id = current_user.tenant_id

    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant ID required")

    # Implementation...
    email_service = EmailService(db)
    provider = await email_service.get_provider(tenant_id, provider_name)
    result = await email_service.send_email(...)

    return {
        "status": "sent",
        "message_id": result.get("message_id"),
        "provider": provider_name,
        "sent_at": datetime.utcnow().isoformat()
    }
```

**Frontend Usage:**
```typescript
// Call custom API endpoint from frontend
const response = await apiClient.post('/api/method/email_marketing.api.send_email_via_provider', {
  provider_name: 'sendgrid',
  to_email: 'customer@example.com',
  subject: 'Welcome to our service',
  body_html: '<h1>Welcome!</h1><p>Thank you for joining.</p>',
  body_text: 'Welcome! Thank you for joining.'
});
```

### Example: Webhook Receiver Endpoint

```python
# Webhook receiver for email service providers
# File: backend/src/modules/email_marketing/api.py

@whitelist(allow_guest=True, methods=['POST'])
async def receive_email_webhook(
    provider: str,
    event_type: str,
    event_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Receive webhook from email service provider

    Available as: POST /api/method/email_marketing.api.receive_email_webhook

    This endpoint receives webhooks from email service providers
    (SendGrid, SES) for delivery events, bounces, opens, clicks, etc.

    Args:
        provider: Email provider name (sendgrid, ses)
        event_type: Type of event (delivered, bounce, open, click, unsubscribe)
        event_data: EventBusEvent payload from provider

    Returns:
        Dict with webhook processing status
    """
    email_service = EmailService(db)

    # Process webhook event
    result = await email_service.process_webhook_event(
        provider=provider,
        event_type=event_type,
        event_data=event_data
    )

    return {
        "status": "processed",
        "event_type": event_type,
        "provider": provider,
        "processed_at": datetime.utcnow().isoformat()
    }
```

**External Provider Configuration:**
- **SendGrid**: Configure webhook URL: `https://your-domain.com/api/method/email_marketing.api.receive_sendgrid_webhook`
- **AWS SES**: Configure SNS topic to POST to: `https://your-domain.com/api/method/email_marketing.api.receive_ses_webhook`

### Example: Campaign Trigger Endpoint

```python
# Campaign trigger endpoint
# File: backend/src/modules/email_marketing/api.py

@whitelist(allow_guest=False, methods=['POST'])
async def trigger_campaign_send(
    campaign_id: str,
    send_immediately: bool = False,
    scheduled_at: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_session)
) -> Dict[str, Any]:
    """Trigger email campaign send

    Available as: POST /api/method/email_marketing.api.trigger_campaign_send

    Args:
        campaign_id: Email campaign ID
        send_immediately: If True, send immediately; if False, schedule
        scheduled_at: ISO datetime string for scheduled send (optional)

    Returns:
        Dict with campaign send status
    """
    campaign_service = CampaignService(db)

    if send_immediately:
        result = await campaign_service.send_campaign_immediately(
            campaign_id=campaign_id,
            tenant_id=current_user.tenant_id,
            triggered_by=current_user.id
        )
    else:
        scheduled_datetime = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        result = await campaign_service.schedule_campaign_send(
            campaign_id=campaign_id,
            scheduled_at=scheduled_datetime,
            tenant_id=current_user.tenant_id,
            triggered_by=current_user.id
        )

    return {
        "status": "triggered",
        "campaign_id": campaign_id,
        "send_immediately": send_immediately,
        "scheduled_at": scheduled_at,
        "triggered_at": datetime.utcnow().isoformat()
    }
```

### Example: Transactional Email Endpoint

```python
# Transactional email endpoint
# File: backend/src/modules/email_marketing/api.py

@whitelist(allow_guest=False, methods=['POST'])
async def send_transactional_email(
    template_name: str,
    to_email: str,
    variables: Dict[str, Any],
    tenant_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_session)
) -> Dict[str, Any]:
    """Send transactional email

    Available as: POST /api/method/email_marketing.api.send_transactional_email

    Args:
        template_name: Transactional email template name
        to_email: Recipient email address
        variables: Template variables for personalization
        tenant_id: Tenant ID (optional, uses current user's tenant)

    Returns:
        Dict with send status
    """
    email_service = EmailService(db)

    result = await email_service.send_transactional_email(
        template_name=template_name,
        to_email=to_email,
        variables=variables,
        tenant_id=tenant_id or current_user.tenant_id
    )

    return {
        "status": "sent",
        "template_name": template_name,
        "to_email": to_email,
        "message_id": result.get("message_id"),
        "sent_at": datetime.utcnow().isoformat()
    }
```

**Usage Example:**
```typescript
// Send welcome email after user registration
await apiClient.post('/api/method/email_marketing.api.send_transactional_email', {
  template_name: 'welcome_email',
  to_email: newUser.email,
  variables: {
    first_name: newUser.firstName,
    activation_link: activationUrl
  }
});
```

### Available Custom API Endpoints

The Email Marketing module provides the following custom API endpoints:

1. **`send_email_via_provider`** - Send email via configured provider
2. **`test_email_provider_connection`** - Test email provider connection
3. **`receive_email_webhook`** - Generic webhook receiver for email providers
4. **`receive_sendgrid_webhook`** - SendGrid-specific webhook receiver
5. **`receive_ses_webhook`** - AWS SES webhook receiver
6. **`trigger_campaign_send`** - Trigger email campaign send
7. **`trigger_automation_workflow`** - Trigger email automation workflow
8. **`send_transactional_email`** - Send transactional email using template

All endpoints are available at: `/api/method/email_marketing.api.<function_name>`

### Creating Custom Endpoints

To create additional custom endpoints:

1. **Add function to `api.py`:**
```python
@whitelist(allow_guest=False, methods=['POST'])
async def your_custom_endpoint(
    param1: str,
    param2: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_session)
) -> Dict[str, Any]:
    """Your custom endpoint description"""
    # Implementation
    return {"status": "success"}
```

2. **Endpoints are automatically registered** when the module loads
3. **Access via:** `POST /api/method/email_marketing.api.your_custom_endpoint`

### Integration with Other Modules

Custom API endpoints can be called from other modules:

```python
# From another module's service
import httpx

async def trigger_email_campaign_from_crm(campaign_id: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE_URL}/api/method/email_marketing.api.trigger_campaign_send",
            json={"campaign_id": campaign_id, "send_immediately": True},
            headers={"Cookie": f"saraise_session={session_id}"}
        )
        return response.json()
```

---

## Client Scripts

### Example: Campaign Builder UI Enhancements

```typescript
// Client script for campaign builder enhancements
// File: frontend/src/components/email-marketing/campaign-builder/CampaignBuilder.tsx

import { useState, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'
import { toast } from 'sonner'

export function CampaignBuilder() {
  const [campaignContent, setCampaignContent] = useState('')
  const [subjectLine, setSubjectLine] = useState('')
  const [isGeneratingSubject, setIsGeneratingSubject] = useState(false)

  // Auto-generate subject line using AI
  const generateSubjectLine = useMutation({
    mutationFn: async (content: string) => {
      const response = await apiClient.post('/email-marketing/ai/generate-subject', {
        campaign_content: content,
        campaign_type: 'promotional'
      })
      return response.data
    },
    onSuccess: (data) => {
      setSubjectLine(data.subject_line)
      toast.success('Subject line generated!')
    },
    onError: () => {
      toast.error('Failed to generate subject line')
    }
  })

  // Auto-optimize send time
  const optimizeSendTime = useMutation({
    mutationFn: async (campaignData: any) => {
      const response = await apiClient.post('/email-marketing/ai/optimize-send-time', campaignData)
      return response.data
    },
    onSuccess: (data) => {
      toast.success(`Optimal send time: ${new Date(data.optimal_send_time).toLocaleString()}`)
    }
  })

  // Real-time content preview with personalization
  const [previewContent, setPreviewContent] = useState('')
  useEffect(() => {
    if (campaignContent) {
      // Show preview with sample personalization
      const personalized = campaignContent
        .replace('{{name}}', 'John Doe')
        .replace('{{company}}', 'Acme Corp')
      setPreviewContent(personalized)
    }
  }, [campaignContent])

  return (
    <div className="campaign-builder">
      {/* Campaign builder components */}
    </div>
  )
}
```

### Example: Campaign Analytics Dashboard

```typescript
// Client script for campaign analytics enhancements
// File: frontend/src/components/email-marketing/analytics/CampaignAnalytics.tsx

import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'
import { Card } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'

export function CampaignAnalytics({ campaignId }: { campaignId: string }) {
  // Real-time engagement metrics
  const { data: metrics } = useQuery({
    queryKey: ['email-campaign-metrics', campaignId],
    queryFn: async () => {
      const response = await apiClient.get(`/email-marketing/campaigns/${campaignId}/metrics`)
      return response.data
    },
    refetchInterval: 30000 // Poll every 30 seconds
  })

  // Engagement prediction using AI
  const { data: prediction } = useQuery({
    queryKey: ['email-engagement-prediction', campaignId],
    queryFn: async () => {
      const response = await apiClient.post('/email-marketing/ai/predict-engagement', {
        campaign_id: campaignId
      })
      return response.data
    }
  })

  return (
    <div className="campaign-analytics">
      <Card>
        <h3>Campaign Performance</h3>
        <div className="metrics">
          <div>
            <span>Open Rate</span>
            <Progress value={metrics?.open_rate || 0} />
            <span>{metrics?.open_rate || 0}%</span>
          </div>
          <div>
            <span>Click Rate</span>
            <Progress value={metrics?.click_rate || 0} />
            <span>{metrics?.click_rate || 0}%</span>
          </div>
        </div>
      </Card>

      {prediction && (
        <Card>
          <h3>AI Engagement Prediction</h3>
          <p>Predicted open rate: {prediction.predicted_open_rate}%</p>
          <p>Predicted click rate: {prediction.predicted_click_rate}%</p>
          <p>Recommendations: {prediction.recommendations?.join(', ')}</p>
        </Card>
      )}
    </div>
  )
}
```

### Example: A/B Testing UI

```typescript
// Client script for A/B testing interface
// File: frontend/src/components/email-marketing/ab-testing/ABTestBuilder.tsx

import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { toast } from 'sonner'

interface ABTestVariant {
  id: string
  subject_line: string
  content: string
  send_percentage: number
}

export function ABTestBuilder({ campaignId }: { campaignId: string }) {
  const [variants, setVariants] = useState<ABTestVariant[]>([
    { id: 'variant-a', subject_line: '', content: '', send_percentage: 50 },
    { id: 'variant-b', subject_line: '', content: '', send_percentage: 50 }
  ])

  // Generate subject line variations using AI
  const generateSubjectVariations = useMutation({
    mutationFn: async (baseSubject: string) => {
      const response = await apiClient.post('/email-marketing/ai/generate-subject', {
        base_subject: baseSubject,
        variations_count: 3
      })
      return response.data
    },
    onSuccess: (data) => {
      // Populate variants with AI-generated subject lines
      setVariants(prev => prev.map((v, idx) => ({
        ...v,
        subject_line: data.variations[idx] || v.subject_line
      })))
      toast.success('Subject line variations generated!')
    }
  })

  // Track A/B test performance
  const { data: testResults } = useQuery({
    queryKey: ['ab-test-results', campaignId],
    queryFn: async () => {
      const response = await apiClient.get(`/email-marketing/campaigns/${campaignId}/ab-test-results`)
      return response.data
    },
    enabled: !!campaignId,
    refetchInterval: 60000 // Poll every minute
  })

  // Declare winner automatically when statistical significance is reached
  useEffect(() => {
    if (testResults?.statistical_significance && !testResults.winner_declared) {
      const winner = testResults.variants.find((v: any) => v.is_winner)
      if (winner) {
        toast.success(`Variant ${winner.id} is the winner!`)
      }
    }
  }, [testResults])

  return (
    <div className="ab-test-builder">
      <Card>
        <h3>A/B Test Configuration</h3>
        {variants.map((variant, idx) => (
          <div key={variant.id} className="variant-config">
            <h4>Variant {idx === 0 ? 'A' : 'B'}</h4>
            <Input
              label="Subject Line"
              value={variant.subject_line}
              onChange={(e) => {
                const updated = [...variants]
                updated[idx].subject_line = e.target.value
                setVariants(updated)
              }}
            />
            <Input
              label="Send Percentage"
              type="number"
              value={variant.send_percentage}
              onChange={(e) => {
                const updated = [...variants]
                updated[idx].send_percentage = parseInt(e.target.value)
                setVariants(updated)
              }}
            />
          </div>
        ))}

        <Button
          onClick={() => generateSubjectVariations.mutate(variants[0].subject_line)}
          disabled={generateSubjectVariations.isPending}
        >
          Generate Subject Line Variations
        </Button>
      </Card>

      {testResults && (
        <Card>
          <h3>A/B Test Results</h3>
          {testResults.variants.map((variant: any) => (
            <div key={variant.id}>
              <h4>Variant {variant.id}</h4>
              <p>Open Rate: {variant.open_rate}%</p>
              <p>Click Rate: {variant.click_rate}%</p>
              {variant.is_winner && <p className="winner-badge">Winner!</p>}
            </div>
          ))}
        </Card>
      )}
    </div>
  )
}
```

### Example: Email Template Builder

```typescript
// Client script for visual email template builder
// File: frontend/src/components/email-marketing/template-builder/TemplateBuilder.tsx

import { useState, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { toast } from 'sonner'

export function TemplateBuilder() {
  const [templateContent, setTemplateContent] = useState('')
  const [previewMode, setPreviewMode] = useState<'desktop' | 'mobile' | 'text'>('desktop')
  const [personalizationVars, setPersonalizationVars] = useState<string[]>([])

  // Auto-detect personalization variables
  useEffect(() => {
    const vars = templateContent.match(/\{\{(\w+)\}\}/g)?.map(v => v.replace(/[{}]/g, '')) || []
    setPersonalizationVars([...new Set(vars)])
  }, [templateContent])

  // Personalize content using AI
  const personalizeContent = useMutation({
    mutationFn: async (content: string) => {
      const response = await apiClient.post('/email-marketing/ai/personalize-content', {
        template_content: content,
        subscriber_data: {
          name: 'John Doe',
          company: 'Acme Corp',
          industry: 'Technology'
        }
      })
      return response.data
    },
    onSuccess: (data) => {
      setTemplateContent(data.personalized_content)
      toast.success('Content personalized!')
    }
  })

  // Preview with sample data
  const [previewContent, setPreviewContent] = useState('')
  useEffect(() => {
    let preview = templateContent
    personalizationVars.forEach(variable => {
      const sampleValue = {
        name: 'John Doe',
        company: 'Acme Corp',
        email: 'john@acme.com',
        first_name: 'John',
        last_name: 'Doe'
      }[variable] || `[${variable}]`
      preview = preview.replace(new RegExp(`\\{\\{${variable}\\}\\}`, 'g'), sampleValue)
    })
    setPreviewContent(preview)
  }, [templateContent, personalizationVars])

  return (
    <div className="template-builder">
      <div className="builder-toolbar">
        <Button onClick={() => personalizeContent.mutate(templateContent)}>
          Personalize with AI
        </Button>
        <div className="preview-mode-selector">
          <Button
            variant={previewMode === 'desktop' ? 'default' : 'outline'}
            onClick={() => setPreviewMode('desktop')}
          >
            Desktop
          </Button>
          <Button
            variant={previewMode === 'mobile' ? 'default' : 'outline'}
            onClick={() => setPreviewMode('mobile')}
          >
            Mobile
          </Button>
          <Button
            variant={previewMode === 'text' ? 'default' : 'outline'}
            onClick={() => setPreviewMode('text')}
          >
            Text
          </Button>
        </div>
      </div>

      <div className="builder-content">
        <div className="editor-panel">
          <textarea
            value={templateContent}
            onChange={(e) => setTemplateContent(e.target.value)}
            className="template-editor"
            placeholder="Enter email template content..."
          />

          {personalizationVars.length > 0 && (
            <Card>
              <h4>Available Variables</h4>
              <ul>
                {personalizationVars.map(variable => (
                  <li key={variable}>
                    <code>{'{{' + variable + '}}'}</code>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        <div className="preview-panel">
          <div className={`preview-container preview-${previewMode}`}>
            <div dangerouslySetInnerHTML={{ __html: previewContent }} />
          </div>
        </div>
      </div>
    </div>
  )
}
```

### Example: List Management UI Enhancements

```typescript
// Client script for list management enhancements
// File: frontend/src/components/email-marketing/lists/ListManager.tsx

import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { toast } from 'sonner'

export function ListManager() {
  const [selectedListId, setSelectedListId] = useState<string | null>(null)

  // Real-time subscriber count updates
  const { data: listStats } = useQuery({
    queryKey: ['email-list-stats', selectedListId],
    queryFn: async () => {
      if (!selectedListId) return null
      const response = await apiClient.get(`/email-marketing/lists/${selectedListId}/stats`)
      return response.data
    },
    enabled: !!selectedListId,
    refetchInterval: 10000 // Poll every 10 seconds
  })

  // Bulk import with progress tracking
  const bulkImport = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('list_id', selectedListId!)

      const response = await apiClient.post('/email-marketing/lists/import', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round(
            (progressEvent.loaded * 100) / (progressEvent.total || 1)
          )
          // Update UI with progress
        }
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Subscribers imported successfully!')
    },
    onError: () => {
      toast.error('Import failed')
    }
  })

  // Segment builder with visual criteria
  const [segmentCriteria, setSegmentCriteria] = useState<any[]>([])

  const addCriteria = (field: string, operator: string, value: any) => {
    setSegmentCriteria([...segmentCriteria, { field, operator, value }])
  }

  return (
    <div className="list-manager">
      <Card>
        <h3>List Statistics</h3>
        {listStats && (
          <div className="stats">
            <div>Total Subscribers: {listStats.total_subscribers}</div>
            <div>Active: {listStats.active_subscribers}</div>
            <div>Unsubscribed: {listStats.unsubscribed_count}</div>
            <div>Bounced: {listStats.bounced_count}</div>
          </div>
        )}
      </Card>

      <Card>
        <h3>Segment Builder</h3>
        <div className="criteria-builder">
          {segmentCriteria.map((criteria, idx) => (
            <div key={idx} className="criterion">
              <select value={criteria.field} onChange={(e) => {
                const updated = [...segmentCriteria]
                updated[idx].field = e.target.value
                setSegmentCriteria(updated)
              }}>
                <option value="email">Email</option>
                <option value="first_name">First Name</option>
                <option value="last_name">Last Name</option>
                <option value="engagement_score">Engagement Score</option>
              </select>
              <select value={criteria.operator} onChange={(e) => {
                const updated = [...segmentCriteria]
                updated[idx].operator = e.target.value
                setSegmentCriteria(updated)
              }}>
                <option value="equals">Equals</option>
                <option value="contains">Contains</option>
                <option value="greater_than">Greater Than</option>
                <option value="less_than">Less Than</option>
              </select>
              <input
                type="text"
                value={criteria.value}
                onChange={(e) => {
                  const updated = [...segmentCriteria]
                  updated[idx].value = e.target.value
                  setSegmentCriteria(updated)
                }}
              />
            </div>
          ))}
          <Button onClick={() => addCriteria('email', 'contains', '')}>
            Add Criteria
          </Button>
        </div>
      </Card>
    </div>
  )
}
```

### Client Script Hooks

Client scripts are loaded via UI hooks defined in `hooks.py`:

- **App-wide scripts**: `app_include_js` and `app_include_css` for global enhancements
- **Resource-specific scripts**: `resource_js` for form-level customizations
- **List view scripts**: `resource_list_js` for list view enhancements

See `backend/src/modules/email_marketing/hooks.py` for the complete hook configuration.

---

## Webhooks

The Email Marketing module provides webhook receiver endpoints to handle email delivery notifications, bounces, opens, clicks, and unsubscribe events from email service providers (SendGrid, AWS SES, SMTP).

### Webhook Receiver Endpoints

The module exposes three webhook receiver endpoints via the `@whitelist` decorator:

#### 1. Generic Email Webhook (`receive_email_webhook`)

Receives webhooks from any email service provider.

**Endpoint**: `/api/v1/email-marketing/webhooks/receive`

**Method**: POST

**Parameters**:
- `provider`: Email provider name (`sendgrid`, `ses`, `smtp`)
- `event_type`: EventBusEvent type (`delivered`, `bounce`, `open`, `click`, `unsubscribe`, `spam_complaint`, etc.)
- `event_data`: EventBusEvent payload from provider

**Example Request**:
```python
import requests

webhook_url = "http://localhost:20001/api/v1/email-marketing/webhooks/receive"

response = requests.post(webhook_url, json={
    "provider": "sendgrid",
    "event_type": "bounce",
    "event_data": {
        "email": "user@example.com",
        "campaign_id": "campaign_123",
        "bounce_type": "hard",
        "bounce_reason": "Invalid recipient",
        "timestamp": "2025-01-15T10:30:00Z"
    }
})
```

#### 2. SendGrid Webhook (`receive_sendgrid_webhook`)

Receives SendGrid webhook events in their standard format.

**Endpoint**: `/api/v1/email-marketing/webhooks/sendgrid`

**Method**: POST

**Parameters**:
- `webhook_data`: List of SendGrid webhook events

**Example Request**:
```python
# SendGrid webhook format
sendgrid_webhook = [
    {
        "email": "user@example.com",
        "event": "bounce",  # processed, delivered, bounce, open, click, etc.
        "timestamp": 1705315800,
        "smtp-id": "<message_id@sendgrid.net>",
        "sg_event_id": "event_id_123",
        "sg_message_id": "message_id_123",
        "reason": "550 5.1.1 User unknown",
        "status": "5.0.0",
        "campaign_id": "campaign_123"
    }
]

response = requests.post(
    "http://localhost:20001/api/v1/email-marketing/webhooks/sendgrid",
    json=sendgrid_webhook
)
```

**SendGrid Webhook Configuration**:

1. Log in to SendGrid Dashboard
2. Navigate to Settings → Mail Settings → EventBusEvent Webhook
3. Add webhook URL: `https://your-domain.com/api/v1/email-marketing/webhooks/sendgrid`
4. Select events to receive:
   - Delivered
   - Bounce
   - Open
   - Click
   - Unsubscribe
   - Spam Report
   - Deferred
   - Processed

#### 3. AWS SES Webhook (`receive_ses_webhook`)

Receives AWS SES webhook events via SNS (Simple Notification Service).

**Endpoint**: `/api/v1/email-marketing/webhooks/ses`

**Method**: POST

**Parameters**:
- `notification_type`: SNS notification type (`Bounce`, `Complaint`, `Delivery`)
- `notification_data`: SNS notification payload

**Example Request**:
```python
# AWS SES SNS notification format
ses_webhook = {
    "notification_type": "Bounce",
    "notification_data": {
        "Type": "Notification",
        "MessageId": "sns_message_id",
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:bounces",
        "Message": {
            "notificationType": "Bounce",
            "bounce": {
                "bounceType": "Permanent",
                "bounceSubType": "General",
                "bouncedRecipients": [
                    {
                        "emailAddress": "user@example.com",
                        "status": "5.1.1",
                        "action": "failed",
                        "diagnosticCode": "smtp; 550 5.1.1 user unknown"
                    }
                ],
                "timestamp": "2025-01-15T10:30:00.000Z",
                "feedbackId": "feedback_id_123"
            },
            "mail": {
                "messageId": "message_id_123",
                "timestamp": "2025-01-15T10:30:00.000Z",
                "source": "noreply@example.com",
                "destination": ["user@example.com"]
            }
        }
    }
}

response = requests.post(
    "http://localhost:20001/api/v1/email-marketing/webhooks/ses",
    json=ses_webhook
)
```

**AWS SES Webhook Configuration**:

1. Create SNS Topic in AWS Console
2. Subscribe HTTP/HTTPS endpoint to topic: `https://your-domain.com/api/v1/email-marketing/webhooks/ses`
3. Configure SES Bounce and Complaint notifications to publish to SNS topic
4. Verify SNS subscription (confirm subscription email)

### Supported Webhook Events

The webhook receiver endpoints process the following event types:

- **delivered**: Email successfully delivered to recipient
- **bounce**: Email bounced (hard or soft bounce)
- **open**: Email was opened by recipient
- **click**: Link in email was clicked
- **unsubscribe**: Recipient unsubscribed from emails
- **spam_complaint**: Recipient marked email as spam
- **deferred**: Email delivery delayed
- **processed**: Email processed by provider

### EventBusEvent Processing

Webhook events are processed by the `EmailService.process_webhook_event()` method, which:

1. **Validates event data**: Ensures required fields are present
2. **Updates email activity**: Records event in `EmailActivity` table
3. **Updates campaign statistics**: Updates campaign metrics (opens, clicks, bounces)
4. **Handles bounces**: Adds email to suppression list if hard bounce
5. **Handles unsubscribes**: Creates unsubscribe record
6. **Publishes events**: Publishes events to EventBusEvent Bus for cross-module consumption

### Example: Webhook EventBusEvent Processing

```python
# Server script that processes webhook events
def on_email_bounced(event_data):
    """Handle email bounce webhook"""
    email = event_data.get("email")
    bounce_type = event_data.get("bounce_type")
    campaign_id = event_data.get("campaign_id")

    # Add to suppression list if hard bounce
    if bounce_type == "hard":
        add_to_suppression_list(email, reason="Hard bounce")

    # Update campaign statistics
    update_campaign_stats(campaign_id, bounce_count=1)

    # Notify campaign owner
    notify_campaign_owner(campaign_id, f"Hard bounce: {email}")
```

### Webhook Security

Webhook endpoints are secured with:

1. **Guest Access**: Webhooks allow guest access (`allow_guest=True`) since providers need to call them without authentication
2. **IP Whitelisting**: Configure email provider IP whitelisting in production
3. **Signature Verification**: Verify webhook signatures from SendGrid/SES (to be implemented)
4. **Rate Limiting**: Apply rate limiting to prevent abuse

### Example: Webhook Configuration for Email Providers

```python
# Webhook configuration for email provider callbacks
webhook_config = {
    "name": "email_provider_status_callback",
    "resource_type": "EmailSendLog",
    "event": "after_insert",
    "url": "https://your-domain.com/api/v1/email-marketing/webhooks/receive",
    "method": "POST",
    "headers": {
        "Authorization": "Bearer YOUR_EMAIL_PROVIDER_KEY",
        "Content-Type": "application/json"
    },
    "request_body": {
        "provider": "sendgrid",
        "event_type": "{{ doc.event_type }}",
        "event_data": {
            "message_id": "{{ doc.id }}",
            "campaign_id": "{{ doc.campaign_id }}",
            "recipient_email": "{{ doc.recipient_email }}",
            "status": "{{ doc.status }}",
            "provider_message_id": "{{ doc.provider_message_id }}"
        }
    },
    "enabled": True,
    "timeout": 30,
    "retry_count": 3
}
```

---

## EventBusEvent Bus Integration

The Email Marketing module automatically publishes email events to the Redis EventBusEvent Bus for cross-module consumption. Events are published by the `EmailService.track_email()` method whenever email activities occur (sent, opened, clicked, bounced, etc.).

### Automatic EventBusEvent Publishing

All email activities automatically trigger event bus publications:

- **`email.sent`** - Published when an email is successfully sent
- **`email.delivered`** - Published when an email is delivered to recipient's mailbox
- **`email.opened`** - Published when a recipient opens an email
- **`email.clicked`** - Published when a recipient clicks a link in an email
- **`email.bounced`** - Published when an email bounces (hard or soft)
- **`email.unsubscribed`** - Published when a recipient unsubscribes

### EventBusEvent Payload Structure

All email events follow a consistent payload structure:

```python
{
    "campaign_id": "campaign_123",
    "recipient_email": "user@example.com",
    "activity_type": "opened",  # sent, delivered, opened, clicked, bounced, unsubscribed
    "activity_id": "activity_456",
    "timestamp": "2025-01-15T10:30:00Z",
    "link_url": "https://example.com/product",  # Only for clicked events
    "ip_address": "192.168.1.1",  # For opened/clicked events
    # Additional fields based on activity type:
    "bounce_type": "hard",  # For bounced events
    "bounce_reason": "Invalid recipient",  # For bounced events
    "subject": "Welcome to Our Newsletter",  # For sent events
    "recipient_name": "John Doe",  # For sent events
    "provider": "sendgrid",  # For sent events
    "reason": "No longer interested"  # For unsubscribed events
}
```

### EventBusEvent Metadata

All events include metadata for additional context:

```python
{
    "contact_id": "contact_789",
    "customer_id": "customer_101",
    "lead_id": "lead_202",
    "user_agent": "Mozilla/5.0...",
    "activity_data": {
        # Additional activity-specific data
    }
}
```

### Subscribing to Email Events

You can subscribe to email events in other modules or customizations:

**Example: CRM Module - Update Contact Engagement Score**

```python
# In CRM module or customization script
from src.core.event_bus import EventBus
from src.core.event_bus import EventBus

async def update_contact_engagement_on_email_open(event_data: Dict[str, Any], db: AsyncSession):
    """Update contact engagement score when email is opened"""
    recipient_email = event_data.get('recipient_email')
    campaign_id = event_data.get('campaign_id')
    contact_id = event_data.get('metadata', {}).get('contact_id')

    if contact_id:
        # Update contact engagement score
        from src.modules.crm.services.contact_service import ContactService
        contact_service = ContactService(db)

        await contact_service.increment_engagement_score(
            contact_id=contact_id,
            points=5,  # 5 points for opening an email
            reason="email_opened",
            metadata={"campaign_id": campaign_id}
        )

        logger.info(f"Updated engagement score for contact {contact_id} after email open")

# Subscribe to email.opened events
event_bus = EventBus()
event_bus.subscribe("email.opened", update_contact_engagement_on_email_open)
```

**Example: Marketing Analytics Module - Track Email Metrics**

```python
# In Marketing Analytics module
async def track_email_metrics(event_data: Dict[str, Any], db: AsyncSession):
    """Track email metrics for analytics"""
    activity_type = event_data.get('activity_type')
    campaign_id = event_data.get('campaign_id')
    tenant_id = event_data.get('tenant_id')

    from src.modules.marketing_analytics.services.analytics_service import AnalyticsService
    analytics_service = AnalyticsService(db)

    # Map activity types to metrics
    metric_map = {
        'sent': 'emails_sent',
        'delivered': 'emails_delivered',
        'opened': 'emails_opened',
        'clicked': 'emails_clicked',
        'bounced': 'emails_bounced',
        'unsubscribed': 'emails_unsubscribed'
    }

    metric_name = metric_map.get(activity_type)
    if metric_name:
        await analytics_service.record_metric(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            metric_name=metric_name,
            value=1,
            timestamp=event_data.get('timestamp')
        )

# Subscribe to all email events
event_bus = EventBus()
for event_type in ['email.sent', 'email.delivered', 'email.opened', 'email.clicked', 'email.bounced', 'email.unsubscribed']:
    event_bus.subscribe(event_type, track_email_metrics)
```

**Example: Lead Nurturing Module - Trigger Automation on Email Click**

```python
# In Lead Nurturing module
async def trigger_nurturing_workflow_on_email_click(event_data: Dict[str, Any], db: AsyncSession):
    """Trigger lead nurturing workflow when email is clicked"""
    recipient_email = event_data.get('recipient_email')
    campaign_id = event_data.get('campaign_id')
    link_url = event_data.get('link_url')
    lead_id = event_data.get('metadata', {}).get('lead_id')

    # Only trigger for specific campaign types (e.g., product launch)
    campaign = await get_campaign(campaign_id, db)
    if campaign and campaign.campaign_type == 'product_launch':
        # Trigger nurturing workflow
        from src.modules.lead_nurturing.services.workflow_service import WorkflowService
        workflow_service = WorkflowService(db)

        await workflow_service.trigger_workflow(
            workflow_name="product_interest_nurturing",
            lead_id=lead_id,
            trigger_data={
                "source": "email_click",
                "campaign_id": campaign_id,
                "link_url": link_url
            }
        )

        logger.info(f"Triggered nurturing workflow for lead {lead_id} after email click")

# Subscribe to email.clicked events
event_bus = EventBus()
event_bus.subscribe("email.clicked", trigger_nurturing_workflow_on_email_click)
```

### EventBusEvent Bus Configuration

The Email Marketing module uses the Redis EventBusEvent Bus for distributed event communication:

```python
from src.core.event_bus import EventBus

# EventBus is initialized in EmailService
event_bus = EventBus()

# Events are published with tenant isolation
await event_bus.publish(
    event_type="email.opened",
    data={
        "campaign_id": campaign_id,
        "recipient_email": recipient_email,
        # ... other event data
    },
    tenant_id=tenant_id,  # Ensures tenant isolation
    metadata={
        "contact_id": contact_id,
        # ... additional metadata
    }
)
```

### Error Handling

EventBusEvent publishing failures are logged but do not block email operations:

```python
# In EmailService.track_email()
try:
    await self.event_bus.publish(...)
except Exception as e:
    # Log error but don't fail the tracking operation
    logger.error(f"Failed to publish {event_type} event to event bus: {e}", exc_info=True)
```

This ensures that email sending and tracking continue even if the event bus is temporarily unavailable.

### Cross-Module Integration Examples

**CRM Integration**: Subscribe to `email.opened` and `email.clicked` events to update contact engagement scores.

**Marketing Analytics Integration**: Subscribe to all email events to track campaign performance metrics.

**Lead Nurturing Integration**: Subscribe to `email.clicked` events to trigger nurturing workflows based on email engagement.

**Campaign Management Integration**: Subscribe to `email.sent` and `email.completed` events to update multi-channel campaign status.

**MDM Integration**: Subscribe to `email.bounced` events to update contact data quality scores.

### Best Practices

1. **Always include tenant_id** when subscribing to events to ensure tenant isolation
2. **Handle errors gracefully** - event handlers should not fail critical operations
3. **Use event metadata** for additional context without bloating event data
4. **Subscribe to specific events** - only subscribe to events you need to avoid unnecessary processing
5. **Log event processing** - log when events are received and processed for debugging
6. **Test event handlers** - ensure event handlers work correctly in development before production

---

## AI-Powered Code Generation

Ask Amani can generate customization code for Email Marketing using natural language prompts. This enables rapid development of server scripts, client scripts, and custom API endpoints without manual coding.

### Server Script Generation

Ask Amani can generate server scripts for email personalization, campaign automation, and delivery optimization.

**Example Prompts for Server Scripts**:

1. **Send Time Optimization**:
   ```
   "Create a server script that uses the email_send_time_optimizer AI agent to automatically optimize email send times based on recipient timezones and engagement history. The script should run before campaign sending and update the scheduled_send_time field."
   ```

2. **Content Personalization**:
   ```
   "Create a server script that uses the email_content_personalizer AI agent to personalize email content for each recipient based on their name, segment, and email history. The script should run on the EmailCampaign before_save hook and replace personalization variables in the email body."
   ```

3. **Bounce Handling**:
   ```
   "Create a server script that automatically handles email bounces. Mark recipients as invalid after hard bounces or 3 soft bounces, and update campaign bounce metrics. The script should run on the EmailBounce after_insert hook."
   ```

4. **Engagement Prediction**:
   ```
   "Create a server script that uses the email_engagement_predictor AI agent to predict open and click rates for campaigns before sending, and provide optimization recommendations. The script should run on the EmailCampaign before_save hook when status is 'draft'."
   ```

5. **A/B Testing Automation**:
   ```
   "Create a server script that automatically runs A/B tests on email campaigns, comparing subject lines and content variations, and selects the winning variant based on engagement metrics after 24 hours. The script should run on a scheduler event."
   ```

**AI Agent Response for Server Scripts**:
Ask Amani will generate:
- Complete server script code with proper event hooks (`before_save`, `after_save`, `validate`, etc.)
- Integration with Email Marketing AI agents (`email_send_time_optimizer`, `email_content_personalizer`, etc.)
- Error handling and validation
- Logging and audit trail
- Documentation and comments
- Test cases

**Example Generated Server Script**:
```python
# Generated by Ask Amani
# Server script: Email send time optimization

from src.modules.email_marketing.services.ai_agent_service import AIAgentService
from src.core.logger import logger

async def optimize_campaign_send_time(doc, method, db):
    """Optimize email campaign send time using AI agent"""
    if doc.resource != "EmailCampaign":
        return

    if doc.status != "scheduled" or not doc.scheduled_send_time:
        return

    try:
        # Get segment or list for send time optimization
        segment_id = doc.segment_id or None
        list_id = doc.list_id or None

        if not segment_id and not list_id:
            logger.warning(f"Campaign {doc.name} has no segment or list for send time optimization")
            return

        # Call AI agent to optimize send time
        ai_service = AIAgentService(db)
        result = await ai_service.execute_agent(
            agent_name="email_send_time_optimizer",
            input_data={
                "segment_id": segment_id,
                "list_id": list_id,
                "campaign_id": doc.id,
                "tenant_id": doc.tenant_id
            }
        )

        if result and result.get("optimal_send_time"):
            # Update campaign scheduled send time
            doc.scheduled_send_time = result["optimal_send_time"]
            logger.info(f"Optimized send time for campaign {doc.name} to {result['optimal_send_time']}")

    except Exception as e:
        logger.error(f"Failed to optimize send time for campaign {doc.name}: {e}", exc_info=True)
        # Don't fail the save operation
```

### Client Script Generation

Ask Amani can generate client scripts for template enhancements, A/B testing UI, and campaign analytics dashboards.

**Example Prompts for Client Scripts**:

1. **Template Builder Enhancement**:
   ```
   "Create a client script that enhances the email template builder with AI-powered subject line suggestions. When a user types email content, show AI-generated subject line variations using the email_subject_line_generator agent."
   ```

2. **A/B Testing UI**:
   ```
   "Create a client script that adds A/B testing controls to the campaign creation form. Allow users to create subject line and content variations, set test group sizes, and view real-time performance metrics."
   ```

3. **Campaign Analytics Dashboard**:
   ```
   "Create a client script that displays a real-time campaign analytics dashboard with open rates, click rates, bounce rates, and engagement predictions using the email_engagement_predictor agent."
   ```

4. **Template Preview Enhancement**:
   ```
   "Create a client script that adds a live preview feature to the email template builder, showing how the template will look with different personalization variables and on different devices (desktop, mobile, tablet)."
   ```

5. **Send Time Optimization UI**:
   ```
   "Create a client script that shows optimal send time recommendations in the campaign scheduling form. Use the email_send_time_optimizer agent to suggest the best send times based on recipient engagement history."
   ```

**AI Agent Response for Client Scripts**:
Ask Amani will generate:
- Complete TypeScript/React component code
- Integration with Email Marketing API endpoints
- UI components using Radix UI and Tailwind CSS
- Error handling and loading states
- TypeScript type definitions
- Documentation and comments

**Example Generated Client Script**:
```typescript
// Generated by Ask Amani
// Client script: AI-powered subject line suggestions

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { apiClient } from '@/lib/api-client'
import { toast } from 'sonner'

export function SubjectLineSuggestions({ campaignContent, onSelect }: {
  campaignContent: string
  onSelect: (subjectLine: string) => void
}) {
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(false)

  const generateSuggestions = async () => {
    if (!campaignContent) {
      toast.error('Please enter campaign content first')
      return
    }

    setIsLoading(true)
    try {
      const response = await apiClient.post('/email-marketing/ai/generate-subject', {
        campaign_content: campaignContent
      })
      setSuggestions(response.data.suggestions || [])
    } catch (error) {
      toast.error('Failed to generate subject line suggestions')
    } finally {
      setIsLoading(false)
  }

  return (
    <Card className="p-4">
      <div className="space-y-2">
        <Button onClick={generateSuggestions} disabled={isLoading}>
          {isLoading ? 'Generating...' : 'Generate Subject Line Suggestions'}
        </Button>
        {suggestions.length > 0 && (
          <div className="space-y-2">
            <h4 className="font-semibold">AI-Generated Suggestions:</h4>
            {suggestions.map((suggestion, index) => (
              <div key={index} className="flex items-center justify-between p-2 border rounded">
                <span>{suggestion}</span>
                <Button size="sm" onClick={() => onSelect(suggestion)}>
                  Use
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  )
}
```

### Custom API Endpoint Generation

Ask Amani can generate custom API endpoints for email service integrations, webhook receivers, and campaign triggers.

**Example Prompts for Custom API Endpoints**:

1. **Email Service Provider Integration**:
   ```
   "Create a custom API endpoint that integrates with SendGrid to send transactional emails. The endpoint should accept template name, recipient email, and variables, then send the email via SendGrid API and track delivery."
   ```

2. **Webhook Receiver**:
   ```
   "Create a custom API endpoint that receives webhooks from Mailchimp for email delivery events. The endpoint should process bounce events, unsubscribe events, and open/click events, then update Email Marketing records accordingly."
   ```

3. **Campaign Trigger**:
   ```
   "Create a custom API endpoint that triggers an email campaign from an external system. The endpoint should accept campaign ID, validate the campaign is ready to send, and trigger the campaign sending workflow."
   ```

4. **Bulk Email Sender**:
   ```
   "Create a custom API endpoint that sends bulk emails to a list of recipients. The endpoint should accept recipient list, template ID, and personalization variables, then send emails in batches to avoid rate limits."
   ```

5. **Email Validation Service**:
   ```
   "Create a custom API endpoint that validates email addresses using an external validation service. The endpoint should accept a list of email addresses, validate them, and return validation results with reasons for invalid emails."
   ```

**AI Agent Response for Custom API Endpoints**:
Ask Amani will generate:
- Complete `@whitelist` decorated function
- Request/response DRF serializers
- Integration with Email Marketing services
- Error handling and validation
- Logging and audit trail
- API documentation

**Example Generated Custom API Endpoint**:
```python
# Generated by Ask Amani
# Custom API endpoint: SendGrid transactional email integration

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
from typing import Dict, Any, Optional
from src.core.session_manager import get_current_user_from_session
from src.modules.email_marketing.services import EmailService

class SendGridEmailRequest(serializers.Serializer):
    template_name = serializers.CharField()
    to_email = serializers.EmailField()
    variables = serializers.JSONField(default=dict)
    tenant_id: str

@whitelist(allow_guest=False, methods=['POST'])
async def send_sendgrid_transactional_email(
    request: SendGridEmailRequest,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Send transactional email via SendGrid

    This endpoint sends transactional emails using SendGrid API.
    It integrates with Email Marketing module to track delivery.

    Args:
        template_name: Name of the transactional email template
        to_email: Recipient email address
        variables: Personalization variables for the template
        tenant_id: Tenant ID for multi-tenant isolation

    Returns:
        Dict with email send status and message ID
    """
    try:
        email_service = EmailService(db)

        # Get transactional template
        template = await email_service.get_transactional_template(
            template_name=request.template_name,
            tenant_id=request.tenant_id
        )

        if not template:
            raise ValueError(f"Template {request.template_name} not found")

        # Render template with variables
        subject = template.subject.format(**request.variables)
        body_html = template.body_html.format(**request.variables)

        # Send via SendGrid
        result = await email_service.send_email_via_provider(
            provider="sendgrid",
            to_email=request.to_email,
            subject=subject,
            body_html=body_html,
            tenant_id=request.tenant_id
        )

        return {
            "status": "sent",
            "message_id": result.get("message_id"),
            "sent_at": result.get("sent_at")
        }

    except Exception as e:
        logger.error(f"Failed to send SendGrid email: {e}", exc_info=True)
        raise
```

### Using Ask Amani for Customization

To generate customization code using Ask Amani:

1. **Access Ask Amani**: Open the Ask Amani interface in the SARAISE application
2. **Provide Context**: Mention that you want to customize the Email Marketing module
3. **Describe Requirements**: Use natural language to describe what you want to achieve
4. **Specify Type**: Indicate whether you need a server script, client script, or custom API endpoint
5. **Review Generated Code**: Ask Amani will generate complete, production-ready code
6. **Test and Deploy**: Test the generated code and deploy it to your tenant

**Best Practices for AI-Generated Customizations**:

1. **Be Specific**: Provide detailed requirements for better code generation
2. **Include Examples**: Mention specific Email Marketing Resources, fields, or services you want to use
3. **Specify Integration Points**: If integrating with other modules, mention them explicitly
4. **Request Error Handling**: Ask for comprehensive error handling and logging
5. **Request Documentation**: Ask for inline comments and documentation
6. **Test Thoroughly**: Always test AI-generated code before deploying to production
7. **Review Security**: Ensure generated code follows SARAISE security standards (RBAC, tenant isolation, audit logging)

### Integration with Email Marketing AI Agents

AI-generated customizations can integrate with Email Marketing AI agents:

- **`email_send_time_optimizer`**: Use in server scripts to optimize campaign send times
- **`email_subject_line_generator`**: Use in client scripts to generate subject line suggestions
- **`email_content_personalizer`**: Use in server scripts to personalize email content
- **`email_engagement_predictor`**: Use in client scripts to show engagement predictions

**Example: Integrating AI Agent in Server Script**:
```python
# Generated by Ask Amani with AI agent integration
from src.modules.email_marketing.services.ai_agent_service import AIAgentService

async def personalize_campaign_content(doc, method, db):
    """Personalize campaign content using AI agent"""
    if doc.resource != "EmailCampaign" or method != "before_save":
        return

    ai_service = AIAgentService(db)
    result = await ai_service.execute_agent(
        agent_name="email_content_personalizer",
        input_data={
            "campaign_id": doc.id,
            "template_id": doc.template_id,
            "segment_id": doc.segment_id,
            "tenant_id": doc.tenant_id
        }
    )

    if result and result.get("personalized_content"):
        doc.body_html = result["personalized_content"]
```

---

## Demo Customizations

### Demo Client Script: Marketing Campaign UI Enhancements

This demo script is included in the demo tenant to showcase marketing campaign UI enhancements:

```typescript
// Demo client script: Marketing Campaign UI Enhancements
// File: frontend/src/components/email-marketing/demo/CampaignUIEnhancements.tsx

export function CampaignUIEnhancements() {
  // Auto-suggest subject lines
  const suggestSubjectLine = async (content: string) => {
    const response = await apiClient.post('/email-marketing/ai/generate-subject', {
      campaign_content: content
    })
    return response.data.subject_line
  }

  // Real-time engagement preview
  const showEngagementPreview = async (campaignId: string) => {
    const response = await apiClient.post('/email-marketing/ai/predict-engagement', {
      campaign_id: campaignId
    })
    return response.data
  }

  // Auto-optimize send time
  const optimizeSendTime = async (segmentId: string) => {
    const response = await apiClient.post('/email-marketing/ai/optimize-send-time', {
      segment_id: segmentId
    })
    return response.data.optimal_send_time
  }

  return (
    <div className="campaign-ui-enhancements">
      {/* Demo UI enhancements */}
    </div>
  )
}
```

This script is automatically loaded for the demo tenant.

---

## Workflow Customization

The Email Marketing module supports workflow customization hooks for campaign approval processes, email sequence workflows, and re-engagement workflows. These hooks allow you to customize workflow behavior at key transition points.

### Available Workflow Hooks

#### 1. Campaign Send Workflow (`email_campaign_send`)

**Hook Types:**
- `before_transition` - Executed before workflow state transition
- `after_transition` - Executed after workflow state transition

**Use Cases:**
- Validate campaign before sending
- Trigger analytics updates after campaign sent
- Send notifications to stakeholders
- Update campaign status

**Example: Campaign Send Validation**

```python
# Server script: Validate campaign before sending
# Register in hooks.py or via customization framework

from src.modules.email_marketing.hooks import register_workflow_hook

async def validate_campaign_before_send(context: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
    """Validate campaign before sending"""
    campaign = context.get('campaign')
    transition_name = context.get('transition_name')

    if transition_name == 'send' and campaign:
        # Validate campaign has required fields
        if not campaign.get('subject_line'):
            raise ValueError("Campaign must have a subject line before sending")

        if not campaign.get('template_id'):
            raise ValueError("Campaign must have a template before sending")

        # Validate recipient list
        if not campaign.get('list_id') and not campaign.get('segment_id'):
            raise ValueError("Campaign must have a recipient list or segment")

        # Check quota limits
        from src.services.user_quota_service import UserQuotaService
        quota_service = UserQuotaService(db)
        can_send, quota_info = await quota_service.check_quota(
            tenant_id=campaign.get('tenant_id'),
            quota_type=QuotaType.API_CALLS
        )

        if not can_send:
            raise ValueError(f"Quota exceeded: {quota_info.get('message', 'Unknown error')}")

    return context

# Register the hook
register_workflow_hook(
    workflow_name="email_campaign_send",
    hook_type="before_transition",
    hook_function=validate_campaign_before_send,
    description="Validate campaign before sending"
)
```

**Example: Post-Send Analytics Update**

```python
# Server script: Update analytics after campaign sent
async def update_analytics_after_send(context: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
    """Update analytics after campaign is sent"""
    campaign = context.get('campaign')
    transition_name = context.get('transition_name')

    if transition_name == 'send' and campaign:
        # Publish event to event bus
        from src.core.event_bus import EventBus, EventType
        event_bus = EventBus()

        await event_bus.publish(EventType.EMAIL_CAMPAIGN_SENT, {
            'campaign_id': campaign.get('id'),
            'tenant_id': campaign.get('tenant_id'),
            'sent_count': campaign.get('sent_count', 0),
            'sent_at': datetime.utcnow().isoformat()
        })

        # Send metrics to Marketing Analytics module
        from src.modules.marketing_analytics.services.analytics_service import AnalyticsService
        analytics_service = AnalyticsService(db)
        await analytics_service.record_campaign_sent(
            campaign_id=campaign.get('id'),
            tenant_id=campaign.get('tenant_id'),
            sent_count=campaign.get('sent_count', 0)
        )

    return context

register_workflow_hook(
    workflow_name="email_campaign_send",
    hook_type="after_transition",
    hook_function=update_analytics_after_send,
    description="Update analytics after campaign sent"
)
```

#### 2. Campaign Approval Workflow (`campaign_approval`)

**Hook Types:**
- `before_transition` - Executed before approval/rejection transition
- `after_transition` - Executed after approval/rejection transition

**Use Cases:**
- Validate approval permissions
- Send approval notifications
- Track approval history
- Enable campaign editing during approval

**Example: Multi-Stage Approval Process**

```python
# Server script: Multi-stage campaign approval
async def validate_approval_permissions(context: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
    """Validate approval permissions before transition"""
    campaign = context.get('campaign')
    transition_name = context.get('transition_name')
    approver = context.get('approver')
    workflow_state = context.get('workflow_state')

    if transition_name == 'approve' and campaign:
        # Check if approver has permission
        approver_role = approver.get('role') if approver else None

        # First stage: Marketing Manager approval required
        if workflow_state == 'pending_marketing_approval':
            if approver_role not in ['tenant_admin', 'tenant_developer']:
                raise ValueError("Only Marketing Manager can approve at this stage")

        # Second stage: Legal/Compliance approval required
        elif workflow_state == 'pending_legal_approval':
            if approver_role not in ['tenant_admin']:
                raise ValueError("Only Legal/Compliance can approve at this stage")

        # Send notification to next approver
        from src.modules.notification.services.notification_service import NotificationService
        notification_service = NotificationService(db)

        await notification_service.send_notification(
            recipient_id=next_approver_id,
            subject=f"Campaign Approval Required: {campaign.get('name')}",
            message=f"Campaign {campaign.get('name')} requires your approval.",
            notification_type="campaign_approval"
        )

    return context

register_workflow_hook(
    workflow_name="campaign_approval",
    hook_type="before_transition",
    hook_function=validate_approval_permissions,
    description="Validate approval permissions for multi-stage approval"
)
```

#### 3. Automation Trigger Workflow (`automation_trigger`)

**Hook Types:**
- `before_transition` - Executed before automation trigger
- `after_transition` - Executed after automation trigger

**Use Cases:**
- Validate automation trigger conditions
- Customize trigger logic
- Log automation events
- Integrate with external systems

**Example: Custom Trigger Logic**

```python
# Server script: Custom automation trigger logic
async def validate_automation_trigger(context: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
    """Validate automation trigger conditions"""
    automation = context.get('automation')
    trigger_event = context.get('trigger_event')

    if trigger_event and automation:
        trigger_type = trigger_event.get('type')
        automation_config = automation.get('trigger_config', {})

        # Date-based trigger: Check if date condition is met
        if trigger_type == 'date_based':
            trigger_date = automation_config.get('trigger_date')
            if trigger_date and datetime.fromisoformat(trigger_date) > datetime.utcnow():
                raise ValueError("Trigger date has not been reached")

        # EventBusEvent-based trigger: Validate event data
        elif trigger_type == 'event_based':
            required_event_data = automation_config.get('required_event_data', [])
            for field in required_event_data:
                if field not in trigger_event.get('data', {}):
                    raise ValueError(f"Missing required event data: {field}")

        # Behavior-based trigger: Check subscriber behavior
        elif trigger_type == 'behavior_based':
            subscriber = trigger_event.get('subscriber')
            behavior_type = automation_config.get('behavior_type')

            # Example: Only trigger if subscriber hasn't opened emails in 30 days
            if behavior_type == 'inactive':
                last_engagement = await get_last_engagement_date(subscriber.get('id'), db)
                if last_engagement and (datetime.utcnow() - last_engagement).days < 30:
                    raise ValueError("Subscriber is not inactive enough")

    return context

register_workflow_hook(
    workflow_name="automation_trigger",
    hook_type="before_transition",
    hook_function=validate_automation_trigger,
    description="Validate automation trigger conditions"
)
```

#### 4. Drip Sequence Workflow (`drip_sequence`)

**Hook Types:**
- `on_state_entry` - Executed when entering a workflow state
- `before_transition` - Executed before state transition
- `after_transition` - Executed after state transition

**Use Cases:**
- Schedule next email in sequence
- Personalize email content based on step
- Handle conditional branching
- Manage sequence delays

**Example: Personalized Drip Sequence**

```python
# Server script: Personalize drip sequence emails
async def personalize_drip_sequence_email(context: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
    """Personalize email content when entering drip sequence step"""
    sequence = context.get('sequence')
    current_step = context.get('current_step')
    subscriber = context.get('subscriber')

    if current_step and sequence and subscriber:
        step_number = current_step.get('step_number')
        template_id = current_step.get('template_id')

        # Get subscriber data for personalization
        subscriber_data = await get_subscriber_data(subscriber.get('id'), db)

        # Personalize template based on subscriber data and step
        from src.modules.email_marketing.services.template_service import TemplateService
        template_service = TemplateService(db)

        personalized_content = await template_service.personalize_template(
            template_id=template_id,
            variables={
                'name': subscriber_data.get('first_name', 'Valued Customer'),
                'company': subscriber_data.get('company', ''),
                'step_number': step_number,
                'total_steps': len(sequence.get('steps', []))
            }
        )

        # Schedule email send with delay
        delay_hours = current_step.get('delay_hours', 24)
        send_time = datetime.utcnow() + timedelta(hours=delay_hours)

        context['personalized_content'] = personalized_content
        context['send_time'] = send_time.isoformat()

    return context

register_workflow_hook(
    workflow_name="drip_sequence",
    hook_type="on_state_entry",
    hook_function=personalize_drip_sequence_email,
    description="Personalize email content when entering drip sequence step"
)
```

#### 5. Re-Engagement Workflow (`reengagement`)

**Hook Types:**
- `on_state_entry` - Executed when entering re-engagement state
- `before_transition` - Executed before re-engagement transition

**Use Cases:**
- Identify inactive subscribers
- Personalize re-engagement emails
- Track re-engagement success
- Manage re-engagement sequences

**Example: Smart Re-Engagement Strategy**

```python
# Server script: Smart re-engagement based on engagement score
async def personalize_reengagement_email(context: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
    """Personalize re-engagement email based on engagement score"""
    subscriber = context.get('subscriber')
    engagement_score = context.get('engagement_score')
    workflow_state = context.get('workflow_state')

    if subscriber and engagement_score:
        # Determine re-engagement strategy based on score
        if engagement_score < 0.2:  # Very low engagement
            # Aggressive re-engagement: special offer
            reengagement_template = "reengagement_special_offer"
            reengagement_subject = f"Special Offer Just for You, {subscriber.get('first_name', 'Friend')}"
        elif engagement_score < 0.5:  # Low engagement
            # Moderate re-engagement: content update
            reengagement_template = "reengagement_content_update"
            reengagement_subject = f"We've Missed You, {subscriber.get('first_name', 'Friend')}"
        else:  # Moderate engagement
            # Gentle re-engagement: preference update
            reengagement_template = "reengagement_preference_update"
            reengagement_subject = f"Help Us Serve You Better, {subscriber.get('first_name', 'Friend')}"

        # Personalize content using AI agent
        from src.modules.email_marketing.services.ai_service import AIService
        ai_service = AIService(db)

        personalized_content = await ai_service.personalize_content(
            agent_name="email_content_personalizer",
            template_name=reengagement_template,
            subscriber_data=subscriber,
            context={
                'engagement_score': engagement_score,
                'last_engagement': subscriber.get('last_engagement_date'),
                'interests': subscriber.get('interests', [])
            }
        )

        context['reengagement_template'] = reengagement_template
        context['reengagement_subject'] = reengagement_subject
        context['personalized_content'] = personalized_content

    return context

register_workflow_hook(
    workflow_name="reengagement",
    hook_type="on_state_entry",
    hook_function=personalize_reengagement_email,
    description="Personalize re-engagement email based on engagement score"
)
```

### Registering Custom Workflow Hooks

To register custom workflow hooks:

1. **Create hook function** in your customization script or module:

```python
async def your_custom_hook(context: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
    """Your custom hook implementation"""
    # Your logic here
    return context
```

2. **Register the hook** using `register_workflow_hook`:

```python
from src.modules.email_marketing.hooks import register_workflow_hook

register_workflow_hook(
    workflow_name="email_campaign_send",  # or "automation_trigger", "drip_sequence", etc.
    hook_type="before_transition",  # or "after_transition", "on_state_entry"
    hook_function=your_custom_hook,
    description="Description of what your hook does"
)
```

3. **Hook execution** - Hooks are automatically executed by the workflow engine at the appropriate transition points.

### Workflow Hook Context

Workflow hooks receive a `context` dictionary containing:

- **`campaign`** - Campaign document (for campaign-related workflows)
- **`automation`** - Automation document (for automation workflows)
- **`sequence`** - Drip sequence document (for sequence workflows)
- **`subscriber`** - Subscriber document (for subscriber-related workflows)
- **`workflow_state`** - Current workflow state
- **`transition_name`** - Name of the transition being executed
- **`approver`** - Approver user (for approval workflows)
- **`trigger_event`** - Trigger event data (for automation triggers)
- **`current_step`** - Current step in sequence (for drip sequences)
- **`engagement_score`** - Engagement score (for re-engagement workflows)

### Integration with Other Customization Points

Workflow hooks can integrate with:

- **Server Scripts**: Call server scripts for complex business logic
- **EventBusEvent Bus**: Publish events to event bus for cross-module communication
- **Custom API Endpoints**: Call custom API endpoints for external integrations
- **AI Agents**: Use AI agents for personalization and optimization

---

## Best Practices

1. **Always validate email data** in server scripts to prevent invalid campaigns
2. **Use event bus** for cross-module integrations (e.g., CRM, analytics, automation)
3. **Log all customizations** for debugging and audit
4. **Test customizations** in development before deploying to production
5. **Handle errors gracefully** - email operations must not fail due to customization errors
6. **Optimize for performance** - email processing scripts should execute quickly (< 1 second)
7. **Use webhooks** for external integrations (email providers, analytics services)
8. **Document custom logic** for marketing teams and developers
9. **Respect unsubscribe requests** - always honor unsubscribe preferences
10. **Comply with email regulations** - ensure CAN-SPAM, GDPR compliance

---

## Integration Points

### CRM Module Integration

- Contact and segment management
- Customer engagement tracking
- Lead scoring and nurturing

### Marketing Automation Module Integration

- Automated email workflows
- Trigger-based campaigns
- Drip campaign sequences

### Campaign Management Module Integration

- Multi-channel campaign coordination
- Campaign performance tracking
- Budget and resource allocation

### Analytics Module Integration

- Email performance analytics
- ROI and conversion tracking
- Engagement reporting

---

## References

- [Customization Framework Documentation](../../01-foundation/customization-framework/README.md)
- [Email Marketing Module Documentation](./README.md)
- [Server Scripts Reference](../../../../development/server-scripts-reference.md)
- [Client Scripts Reference](../../../../development/client-scripts-reference.md)
- [EventBusEvent Bus Documentation](../../01-foundation/customization-framework/event-bus.md)


## Integrations

**Module**: Email Marketing
**Category**: Communication & Marketing
**Version**: 1.0.0

---

## Overview

The Email Marketing module integrates with multiple SARAISE modules to provide comprehensive email marketing capabilities within the larger platform ecosystem. This document details all inter-module integrations, API contracts, and integration patterns.

---

## Integration Architecture

### Integration Patterns

1. **Service-to-Service Integration**: Direct service method calls between modules
2. **EventBusEvent Bus Integration**: Publish/subscribe to events via Redis EventBusEvent Bus
3. **Webhook Integration**: HTTP webhooks for external and cross-module communication
4. **API Integration**: RESTful API calls between modules
5. **Data Synchronization**: Bidirectional data sync for contacts, segments, and metrics

---

## 1. CRM Module Integration

### Purpose

Integrate Email Marketing with CRM to:
- Read contacts and customer data for email campaigns
- Update contact engagement scores based on email performance
- Trigger email campaigns from CRM workflows
- Sync email engagement metrics to CRM

### Integration Service

**Service**: `CRMIntegrationService`
**Location**: `backend/src/modules/email_marketing/services/crm_integration_service.py`

### Integration Points

#### 1.1 Contact Read Integration

**Method**: `get_contacts_for_segment()`

**Purpose**: Read contacts from CRM that match segment criteria

**Signature**:
```python
async def get_contacts_for_segment(
    tenant_id: str,
    criteria: Optional[Dict[str, Any]] = None,
    skip: int = 0,
    limit: int = 1000,
) -> List[Dict[str, Any]]
```

**Parameters**:
- `tenant_id`: Tenant ID for isolation
- `criteria`: Segment criteria (e.g., `{"customer_id": "...", "is_active": True}`)
- `skip`: Pagination offset
- `limit`: Maximum number of contacts to return

**Returns**: List of contact dictionaries with:
- `id`, `email`, `first_name`, `last_name`, `full_name`
- `customer_id`, `phone`, `mobile`
- `job_title`, `department`
- `city`, `state`, `country`
- `is_primary`

**Example Usage**:
```python
from src.modules.email_marketing.services.crm_integration_service import CRMIntegrationService

crm_service = CRMIntegrationService(db)

# Get contacts for a customer
contacts = await crm_service.get_contacts_for_segment(
    tenant_id=tenant_id,
    criteria={"customer_id": "customer_123", "is_active": True},
    limit=1000
)

# Use contacts for email campaign
for contact in contacts:
    if contact["email"]:
        # Add to email list or segment
        pass
```

**Integration Points**:
- Used by `SegmentationService` to build dynamic segments
- Used by `CampaignService` to get recipient lists
- Used by `AutomationService` to enroll contacts in automations

---

#### 1.2 Customer Contacts Integration

**Method**: `get_customer_contacts()`

**Purpose**: Get all contacts for a specific customer

**Signature**:
```python
async def get_customer_contacts(
    tenant_id: str,
    customer_id: str,
    include_inactive: bool = False,
) -> List[Dict[str, Any]]
```

**Example Usage**:
```python
# Get all contacts for a customer
contacts = await crm_service.get_customer_contacts(
    tenant_id=tenant_id,
    customer_id="customer_123",
    include_inactive=False
)
```

---

#### 1.3 Contact by Email Integration

**Method**: `get_contact_by_email()`

**Purpose**: Get a contact by email address

**Signature**:
```python
async def get_contact_by_email(
    tenant_id: str,
    email: str,
) -> Optional[Dict[str, Any]]
```

**Example Usage**:
```python
# Get contact by email
contact = await crm_service.get_contact_by_email(
    tenant_id=tenant_id,
    email="user@example.com"
)
```

---

#### 1.4 Engagement Update Integration

**Purpose**: Update CRM contact engagement scores based on email campaign performance

**Implementation**: Via EventBusEvent Bus subscription

**EventBusEvent Subscription**: `email.opened`, `email.clicked`, `email.bounced`

**EventBusEvent Handler**:
```python
# In CRM module or Email Marketing hooks
async def update_crm_engagement_on_email_event(
    event_data: Dict[str, Any],
    db: AsyncSession
):
    """Update CRM contact engagement score when email is opened/clicked"""
    recipient_email = event_data.get('recipient_email')
    activity_type = event_data.get('activity_type')
    contact_id = event_data.get('metadata', {}).get('contact_id')

    if contact_id:
        from src.modules.crm.services.contact_service import ContactService
        contact_service = ContactService(db)

        # Calculate engagement points
        points = 5 if activity_type == 'opened' else 10 if activity_type == 'clicked' else 0

        if points > 0:
            await contact_service.increment_engagement_score(
                contact_id=contact_id,
                points=points,
                reason=f"email_{activity_type}",
                metadata={"campaign_id": event_data.get('campaign_id')}
            )
```

**Integration Points**:
- EventBusEvent bus events: `email.opened`, `email.clicked`
- CRM ContactService: `increment_engagement_score()`

---

#### 1.5 CRM Workflow Trigger Integration

**Purpose**: Enable CRM lead nurturing workflows to trigger Email Marketing campaigns

**Implementation**: Via EventBusEvent Bus subscription

**EventBusEvent Subscription**: `crm.lead.created`, `crm.lead.status_changed`, `crm.contact.engaged`

**EventBusEvent Handler**:
```python
# In Email Marketing hooks or automation service
async def trigger_email_campaign_on_crm_event(
    event_data: Dict[str, Any],
    db: AsyncSession
):
    """Trigger email campaign when CRM event occurs"""
    event_type = event_data.get('event_type')
    lead_id = event_data.get('lead_id')
    contact_id = event_data.get('contact_id')
    tenant_id = event_data.get('tenant_id')

    if event_type == 'crm.lead.created':
        # Trigger welcome email campaign
        from src.modules.email_marketing.services.automation_service import AutomationService
        automation_service = AutomationService(db)

        # Find welcome automation
        automations = await automation_service.list_automations(
            tenant_id=tenant_id,
            automation_type='welcome',
            status='active'
        )

        if automations:
            # Enroll lead in welcome automation
            await automation_service.enroll_contact(
                enrollment_data=EmailAutomationEnrollRequest(
                    automation_id=automations[0].id,
                    contact_id=contact_id,
                    lead_id=lead_id,
                ),
                tenant_id=tenant_id
            )
```

**Integration Points**:
- EventBusEvent bus events: `crm.lead.created`, `crm.lead.status_changed`
- Email Marketing AutomationService: `enroll_contact()`

---

### API Contracts

**CRM Module APIs Used**:
- `GET /api/v1/crm/contacts` - List contacts
- `GET /api/v1/crm/contacts/{contact_id}` - Get contact
- `PUT /api/v1/crm/contacts/{contact_id}/engagement` - Update engagement score

**Email Marketing APIs Exposed**:
- `POST /api/v1/email-marketing/campaigns` - Create campaign (called by CRM workflows)
- `POST /api/v1/email-marketing/automations/{automation_id}/enroll` - Enroll contact (called by CRM workflows)

---

## 2. Campaign Management Module Integration

### Purpose

Integrate Email Marketing campaigns with Campaign Management for multi-channel orchestration.

### Integration Service

**Service**: `CampaignManagementIntegrationService` (To be implemented)
**Location**: `backend/src/modules/email_marketing/services/campaign_management_integration_service.py`

### Integration Points

#### 2.1 Campaign Registration

**Purpose**: Register Email Marketing campaigns as channels in Campaign Management

**Method**:
```python
async def register_email_campaign(
    tenant_id: str,
    email_campaign_id: str,
    parent_campaign_id: str,
) -> bool:
    """Register email campaign as channel in parent campaign"""
    # Implementation: Create channel in Campaign Management
    pass
```

**Example Usage**:
```python
from src.modules.email_marketing.services.campaign_management_integration_service import (
    CampaignManagementIntegrationService
)

cm_service = CampaignManagementIntegrationService(db)

# Register email campaign in parent campaign
await cm_service.register_email_campaign(
    tenant_id=tenant_id,
    email_campaign_id=email_campaign.id,
    parent_campaign_id=parent_campaign_id
)
```

---

#### 2.2 Campaign Status Sync

**Purpose**: Sync Email Marketing campaign status to Campaign Management

**Implementation**: Via EventBusEvent Bus

**Events Published**:
- `email.campaign.created` → Campaign Management creates channel
- `email.campaign.sent` → Campaign Management updates channel status
- `email.campaign.completed` → Campaign Management marks channel complete

**EventBusEvent Data**:
```python
{
    "campaign_id": "email_campaign_123",
    "parent_campaign_id": "campaign_456",
    "status": "sent",
    "sent_count": 1000,
    "sent_at": "2025-01-15T10:30:00Z"
}
```

---

#### 2.3 Multi-Channel Performance

**Purpose**: Aggregate Email Marketing metrics with other channel metrics

**Integration Points**:
- Campaign Management reads Email Marketing metrics via AnalyticsService
- Combined metrics displayed in Campaign Management dashboard

---

### API Contracts

**Campaign Management APIs Used**:
- `POST /api/v1/campaign-management/campaigns/{campaign_id}/channels` - Create channel
- `PUT /api/v1/campaign-management/campaigns/{campaign_id}/channels/{channel_id}` - Update channel status

**Email Marketing APIs Exposed**:
- `GET /api/v1/email-marketing/campaigns/{campaign_id}/metrics` - Get campaign metrics (called by Campaign Management)

---

## 3. Marketing Analytics Module Integration

### Purpose

Send Email Marketing campaign metrics to Marketing Analytics for:
- Performance tracking
- ROI calculations
- Attribution modeling
- Funnel analysis

### Integration Service

**Service**: `AnalyticsService` + `MarketingAnalyticsService`
**Location**:
- `backend/src/modules/email_marketing/services/analytics_service.py`
- `backend/src/modules/marketing_analytics/services/marketing_analytics_service.py`

### Integration Points

#### 3.1 Metrics Send Integration

**Purpose**: Send campaign metrics (opens, clicks, conversions) to Marketing Analytics

**Method**: `record_campaign_metrics()`

**Implementation**:
```python
# In EmailService or CampaignService
async def send_metrics_to_analytics(
    campaign_id: str,
    tenant_id: str,
    metrics: Dict[str, Any]
):
    """Send campaign metrics to Marketing Analytics"""
    try:
        from src.modules.marketing_analytics.services.marketing_analytics_service import (
            MarketingAnalyticsService
        )

        analytics_service = MarketingAnalyticsService(db)

        # Record campaign metrics
        await analytics_service.record_campaign_metrics(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            campaign_type="email",
            period_start=metrics.get("period_start"),
            period_end=metrics.get("period_end"),
            total_sent=metrics.get("total_sent", 0),
            total_delivered=metrics.get("total_delivered", 0),
            total_opened=metrics.get("total_opened", 0),
            total_clicked=metrics.get("total_clicked", 0),
            total_converted=metrics.get("total_converted", 0),
            total_bounced=metrics.get("total_bounced", 0),
            total_unsubscribed=metrics.get("total_unsubscribed", 0),
        )
    except Exception as e:
        logger.error(f"Failed to send metrics to Marketing Analytics: {e}", exc_info=True)
```

**Integration Points**:
- Called after campaign send completion
- Called periodically for active campaigns
- Called via event bus on `email.campaign.sent`

---

#### 3.2 ROI Feed Integration

**Purpose**: Feed email performance data to marketing ROI calculations

**Method**: `calculate_roi()`

**Implementation**:
```python
# In AnalyticsService
async def send_roi_data_to_analytics(
    tenant_id: str,
    start_date: datetime,
    end_date: datetime,
):
    """Send ROI data to Marketing Analytics"""
    try:
        from src.modules.marketing_analytics.services.marketing_analytics_service import (
            MarketingAnalyticsService
        )

        analytics_service = MarketingAnalyticsService(db)

        # Calculate email marketing ROI
        roi_data = await self.calculate_roi(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Send to Marketing Analytics
        await analytics_service.record_channel_roi(
            tenant_id=tenant_id,
            channel_type="email",
            period_start=start_date,
            period_end=end_date,
            total_revenue=roi_data.get("total_revenue", 0),
            total_cost=roi_data.get("total_cost", 0),
            roi=roi_data.get("roi", 0),
        )
    except Exception as e:
        logger.error(f"Failed to send ROI data to Marketing Analytics: {e}", exc_info=True)
```

**Integration Points**:
- Called periodically (daily/weekly)
- Called via scheduler events
- Marketing Analytics aggregates ROI across all channels

---

### API Contracts

**Marketing Analytics APIs Used**:
- `POST /api/v1/marketing-analytics/aggregate/email-metrics` - Aggregate email metrics
- `POST /api/v1/marketing-analytics/aggregate/campaign-metrics` - Aggregate campaign metrics
- `POST /api/v1/marketing-analytics/roi` - Calculate ROI

**Email Marketing APIs Exposed**:
- `GET /api/v1/email-marketing/campaigns/{campaign_id}/analytics` - Get campaign analytics (called by Marketing Analytics)

---

## 4. Lead Nurturing Module Integration

### Purpose

Integrate Email Marketing with Lead Nurturing for automated email sequences.

### Integration Service

**Service**: `LeadNurturingIntegrationService` (To be implemented)
**Location**: `backend/src/modules/email_marketing/services/lead_nurturing_integration_service.py`

### Integration Points

#### 4.1 Drip Campaign Trigger

**Purpose**: Enable Lead Nurturing workflows to trigger Email Marketing drip campaigns

**Method**:
```python
async def trigger_drip_campaign_from_nurturing(
    tenant_id: str,
    lead_id: str,
    sequence_name: str,
    trigger_data: Dict[str, Any],
) -> str:
    """Trigger email drip campaign from Lead Nurturing sequence"""
    # Find or create automation workflow
    # Enroll lead in automation
    # Return automation ID
    pass
```

**Example Usage**:
```python
from src.modules.email_marketing.services.lead_nurturing_integration_service import (
    LeadNurturingIntegrationService
)

ln_service = LeadNurturingIntegrationService(db)

# Trigger drip campaign from nurturing sequence
automation_id = await ln_service.trigger_drip_campaign_from_nurturing(
    tenant_id=tenant_id,
    lead_id=lead_id,
    sequence_name="welcome_series",
    trigger_data={
        "source": "lead_nurturing",
        "sequence_step": 1
    }
)
```

---

#### 4.2 EventBusEvent Subscription

**Purpose**: Subscribe to Lead Nurturing events to trigger email campaigns

**EventBusEvent Subscription**: `lead_nurturing.sequence.started`, `lead_nurturing.sequence.completed`

**EventBusEvent Handler**:
```python
# In Email Marketing hooks
async def trigger_email_on_nurturing_event(
    event_data: Dict[str, Any],
    db: AsyncSession
):
    """Trigger email campaign when nurturing event occurs"""
    event_type = event_data.get('event_type')
    lead_id = event_data.get('lead_id')
    sequence_name = event_data.get('sequence_name')

    if event_type == 'lead_nurturing.sequence.started':
        # Trigger welcome email
        pass
    elif event_type == 'lead_nurturing.sequence.completed':
        # Trigger follow-up email
        pass
```

---

### API Contracts

**Lead Nurturing APIs Used**:
- `POST /api/v1/lead-nurturing/sequences/{sequence_id}/enroll` - Enroll lead (called by Email Marketing)
- `GET /api/v1/lead-nurturing/sequences/{sequence_id}` - Get sequence details

**Email Marketing APIs Exposed**:
- `POST /api/v1/email-marketing/automations/{automation_id}/enroll` - Enroll contact (called by Lead Nurturing)
- `POST /api/v1/email-marketing/campaigns` - Create campaign (called by Lead Nurturing)

---

## 5. Master Data Management (MDM) Module Integration

### Purpose

Integrate Email Marketing with MDM for:
- Email address validation
- Contact data quality checks
- Contact list deduplication

### Integration Service

**Service**: `MDMIntegrationService` (To be implemented)
**Location**: `backend/src/modules/email_marketing/services/mdm_integration_service.py`

### Integration Points

#### 5.1 Email Validation Integration

**Purpose**: Validate email addresses through MDM for data quality

**Method**:
```python
async def validate_email_addresses(
    tenant_id: str,
    email_addresses: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Validate email addresses via MDM"""
    try:
        from src.modules.master_data.services.mdm_service import MDMService

        mdm_service = MDMService(db)

        validation_results = {}
        for email in email_addresses:
            result = await mdm_service.validate_email(
                tenant_id=tenant_id,
                email=email,
            )
            validation_results[email] = {
                "valid": result.get("valid", False),
                "reason": result.get("reason", ""),
                "quality_score": result.get("quality_score", 0),
            }

        return validation_results
    except ImportError:
        # MDM module not available - return basic validation
        return {email: {"valid": "@" in email, "reason": "Basic check"} for email in email_addresses}
```

**Example Usage**:
```python
from src.modules.email_marketing.services.mdm_integration_service import MDMIntegrationService

mdm_service = MDMIntegrationService(db)

# Validate email addresses before adding to list
emails = ["user1@example.com", "user2@example.com", "invalid-email"]
results = await mdm_service.validate_email_addresses(
    tenant_id=tenant_id,
    email_addresses=emails
)

# Filter out invalid emails
valid_emails = [email for email, result in results.items() if result["valid"]]
```

**Integration Points**:
- Used by `SegmentationService` when building segments
- Used by `CampaignService` before sending campaigns
- Used by list import/export functionality

---

#### 5.2 Deduplication Integration

**Purpose**: Pass email addresses through MDM deduplication checks

**Method**:
```python
async def deduplicate_contact_list(
    tenant_id: str,
    email_addresses: List[str],
) -> List[str]:
    """Deduplicate email addresses via MDM"""
    try:
        from src.modules.master_data.services.mdm_service import MDMService

        mdm_service = MDMService(db)

        # Deduplicate via MDM
        deduplicated = await mdm_service.deduplicate_emails(
            tenant_id=tenant_id,
            emails=email_addresses,
        )

        return deduplicated
    except ImportError:
        # MDM module not available - basic deduplication
        return list(set(email_addresses))
```

**Example Usage**:
```python
# Deduplicate contact list
emails = ["user@example.com", "user@example.com", "another@example.com"]
deduplicated = await mdm_service.deduplicate_contact_list(
    tenant_id=tenant_id,
    email_addresses=emails
)
# Result: ["user@example.com", "another@example.com"]
```

**Integration Points**:
- Used by list import functionality
- Used by segment building
- Used before campaign sending

---

### API Contracts

**MDM APIs Used**:
- `POST /api/v1/master-data/mdm/validate/email` - Validate email address
- `POST /api/v1/master-data/mdm/deduplicate/emails` - Deduplicate email addresses

**Email Marketing APIs Exposed**:
- None (MDM integration is one-way: Email Marketing calls MDM)

---

## 6. Content Management System (CMS) Module Integration

### Purpose

Integrate Email Marketing templates with CMS for:
- Template content reuse
- Template version control
- Content history tracking

### Integration Service

**Service**: `CMSIntegrationService` (To be implemented)
**Location**: `backend/src/modules/email_marketing/services/cms_integration_service.py`

### Integration Points

#### 6.1 Template Reuse Integration

**Purpose**: Integrate Email Marketing templates with CMS for content reuse

**Method**:
```python
async def get_cms_content_for_template(
    tenant_id: str,
    cms_content_id: str,
) -> Dict[str, Any]:
    """Get CMS content for email template"""
    try:
        from src.modules.content_management.services.content_service import ContentService

        content_service = ContentService(db)

        # Get content from CMS
        content = await content_service.get_content(
            content_id=cms_content_id,
            tenant_id=tenant_id,
        )

        return {
            "html": content.get("html_content", ""),
            "text": content.get("text_content", ""),
            "title": content.get("title", ""),
            "version": content.get("version", 1),
        }
    except ImportError:
        return None
```

**Example Usage**:
```python
from src.modules.email_marketing.services.cms_integration_service import CMSIntegrationService

cms_service = CMSIntegrationService(db)

# Get CMS content for template
cms_content = await cms_service.get_cms_content_for_template(
    tenant_id=tenant_id,
    cms_content_id="cms_content_123"
)

# Use in email template
if cms_content:
    template.body_html = cms_content["html"]
    template.body_text = cms_content["text"]
```

---

#### 6.2 Version Control Integration

**Purpose**: Manage email content through CMS version control

**Method**:
```python
async def create_template_version_in_cms(
    tenant_id: str,
    template_id: str,
    template_content: Dict[str, Any],
) -> str:
    """Create template version in CMS"""
    try:
        from src.modules.content_management.services.content_service import ContentService

        content_service = ContentService(db)

        # Create content version in CMS
        version = await content_service.create_content_version(
            tenant_id=tenant_id,
            content_type="email_template",
            content_id=template_id,
            html_content=template_content.get("html", ""),
            text_content=template_content.get("text", ""),
            metadata={
                "template_id": template_id,
                "version": template_content.get("version", 1),
            }
        )

        return version.id
    except ImportError:
        return None
```

**Example Usage**:
```python
# Create template version in CMS
version_id = await cms_service.create_template_version_in_cms(
    tenant_id=tenant_id,
    template_id=template.id,
    template_content={
        "html": template.body_html,
        "text": template.body_text,
        "version": template.version,
    }
)
```

---

### API Contracts

**CMS APIs Used**:
- `GET /api/v1/content-management/content/{content_id}` - Get content
- `POST /api/v1/content-management/content/{content_id}/versions` - Create content version
- `GET /api/v1/content-management/content/{content_id}/versions` - List content versions

**Email Marketing APIs Exposed**:
- `GET /api/v1/email-marketing/templates/{template_id}` - Get template (called by CMS)
- `PUT /api/v1/email-marketing/templates/{template_id}` - Update template (called by CMS)

---

## EventBusEvent Bus Integration

### Events Published by Email Marketing

Email Marketing publishes the following events to the event bus:

1. **`email.sent`** - Email successfully sent
2. **`email.delivered`** - Email delivered to recipient's mailbox
3. **`email.opened`** - Email opened by recipient
4. **`email.clicked`** - Link in email clicked
5. **`email.bounced`** - Email bounced
6. **`email.unsubscribed`** - Recipient unsubscribed

**EventBusEvent Payload Structure**:
```python
{
    "campaign_id": "campaign_123",
    "recipient_email": "user@example.com",
    "activity_type": "opened",
    "activity_id": "activity_456",
    "timestamp": "2025-01-15T10:30:00Z",
    "link_url": "https://example.com/product",  # For clicked events
    "ip_address": "192.168.1.1",  # For opened/clicked events
    "bounce_type": "hard",  # For bounced events
    "bounce_reason": "Invalid recipient",  # For bounced events
    "subject": "Welcome to Our Newsletter",  # For sent events
    "recipient_name": "John Doe",  # For sent events
    "provider": "sendgrid",  # For sent events
    "reason": "No longer interested"  # For unsubscribed events
}
```

**EventBusEvent Metadata**:
```python
{
    "contact_id": "contact_789",
    "customer_id": "customer_101",
    "lead_id": "lead_202",
    "user_agent": "Mozilla/5.0...",
    "activity_data": {
        # Additional activity-specific data
    }
}
```

### Events Subscribed by Email Marketing

Email Marketing subscribes to the following events:

1. **`crm.lead.created`** → Trigger welcome email automation
2. **`crm.lead.status_changed`** → Trigger status-based email campaigns
3. **`crm.contact.engaged`** → Update engagement tracking
4. **`campaign_management.campaign.started`** → Register email channel
5. **`campaign_management.campaign.completed`** → Update email channel status
6. **`lead_nurturing.sequence.started`** → Trigger email drip campaign
7. **`lead_nurturing.sequence.completed`** → Trigger follow-up email

---

## Integration Testing

### Test Scenarios

1. **CRM Integration Tests**:
   - Test reading contacts from CRM
   - Test updating engagement scores
   - Test triggering campaigns from CRM events

2. **Marketing Analytics Integration Tests**:
   - Test sending metrics to Marketing Analytics
   - Test ROI data feed
   - Test metrics aggregation

3. **Campaign Management Integration Tests**:
   - Test registering email campaigns as channels
   - Test status synchronization
   - Test multi-channel performance aggregation

4. **Lead Nurturing Integration Tests**:
   - Test triggering drip campaigns
   - Test event subscription
   - Test sequence enrollment

5. **MDM Integration Tests**:
   - Test email validation
   - Test contact deduplication
   - Test data quality checks

6. **CMS Integration Tests**:
   - Test template content reuse
   - Test version control
   - Test content history tracking

---

## Error Handling

All integrations include comprehensive error handling:

1. **Module Availability Checks**: Verify module is installed before integration
2. **Graceful Degradation**: Fallback behavior when integration fails
3. **Error Logging**: All integration errors logged with context
4. **Retry Logic**: Automatic retries for transient failures
5. **Circuit Breaker**: Prevent cascading failures

---

## Best Practices

1. **Always check module availability** before calling integration services
2. **Use event bus** for asynchronous cross-module communication
3. **Implement retry logic** for external API calls
4. **Log all integration calls** for debugging and audit
5. **Handle errors gracefully** - don't fail email operations due to integration errors
6. **Use tenant isolation** in all integration calls
7. **Validate data** before sending to other modules
8. **Cache integration results** when appropriate to reduce API calls

---

## References

- [Email Marketing Module README](./README.md)
- [CRM Module Documentation](../../03-crm/README.md)
- [Campaign Management Module Documentation](../campaign-management/README.md)
- [Marketing Analytics Module Documentation](../marketing-analytics/README.md)
- [Lead Nurturing Module Documentation](../lead-nurturing/README.md)
- [MDM Module Documentation](../../01-foundation/master-data-management/README.md)
- [CMS Module Documentation](../content-management/README.md)
- [EventBusEvent Bus Documentation](../../01-foundation/customization-framework/event-bus.md)


## Demo Data

**Module**: Email Marketing
**Category**: Communication & Marketing
**Version**: 1.0.0

---

## Overview

This document describes the demo data available for the Email Marketing module in the Demo Tenant (`demo@saraise.com`). The demo data provides comprehensive examples of campaigns, templates, segments, automations, and subscribers to demonstrate all module features.

---

## Demo Tenant Access

**Tenant**: Demo Tenant
**Email**: `demo@saraise.com`
**Password**: `DemoTenant@2025`
**Domain**: `saraise.com`

---

## Demo Data Structure

### Email Templates (3 templates)

1. **Welcome Email Template**
   - **Name**: "Welcome Email Template"
   - **Subject**: "Welcome {{first_name}}!"
   - **Type**: Welcome/Onboarding
   - **Status**: Active
   - **Variables**: `first_name`, `company_name`, `unsubscribe_url`, `preferences_url`
   - **Features**: HTML and text versions, personalization variables

2. **Newsletter Template**
   - **Name**: "Newsletter Template"
   - **Subject**: "{{newsletter_title}}"
   - **Type**: Newsletter
   - **Status**: Active
   - **Variables**: `newsletter_title`, `newsletter_content`, `article1_url`, `article1_title`, etc.
   - **Features**: Multi-article layout, unsubscribe links

3. **Product Launch Template**
   - **Name**: "Product Launch Template"
   - **Subject**: "🎉 Introducing {{product_name}}!"
   - **Type**: Product Announcement
   - **Status**: Active
   - **Variables**: `product_name`, `feature1`, `feature2`, `feature3`, `product_url`
   - **Features**: Call-to-action buttons, feature highlights

---

### Email Segments (4 segments)

1. **VIP Customers**
   - **Type**: Static
   - **Criteria**: `customer_tier == "VIP"`
   - **Status**: Active
   - **Use Case**: Premium campaigns for high-value customers

2. **Newsletter Subscribers**
   - **Type**: Dynamic
   - **Criteria**: `newsletter_subscribed == true`
   - **Status**: Active
   - **Use Case**: Regular newsletter campaigns

3. **Recent Purchasers**
   - **Type**: Dynamic
   - **Criteria**: `last_purchase_date > 30 days ago`
   - **Status**: Active
   - **Use Case**: Follow-up campaigns, cross-sell opportunities

4. **Inactive Subscribers**
   - **Type**: Behavioral
   - **Criteria**: `last_email_open < 90 days ago`
   - **Status**: Active
   - **Use Case**: Re-engagement campaigns

---

### Email Campaigns (5 campaigns)

1. **Welcome Email Series**
   - **Type**: Broadcast
   - **Status**: Sent
   - **Segment**: VIP Customers
   - **Metrics**:
     - Sent: 1,250
     - Delivered: 1,200
     - Opened: 450 (37.5% open rate)
     - Clicked: 180 (15% click rate)
     - Bounced: 50 (4% bounce rate)
   - **Sent Date**: 5 days ago
   - **Features**: Completed campaign with full metrics

2. **Product Launch Announcement**
   - **Type**: Broadcast
   - **Status**: Scheduled
   - **Segment**: Newsletter Subscribers
   - **Scheduled Date**: 2 days from now
   - **Features**: Scheduled campaign ready to send

3. **Monthly Newsletter - January 2025**
   - **Type**: Broadcast
   - **Status**: Draft
   - **Segment**: Newsletter Subscribers
   - **Features**: Draft campaign ready for editing

4. **Abandoned Cart Recovery**
   - **Type**: Automated
   - **Status**: Sending
   - **Segment**: Recent Purchasers
   - **Metrics**:
     - Sent: 320
     - Delivered: 310
     - Opened: 95 (30.6% open rate)
     - Clicked: 42 (13.5% click rate)
   - **Features**: Active automated campaign

5. **Re-engagement Campaign**
   - **Type**: Broadcast
   - **Status**: Draft
   - **Segment**: Inactive Subscribers
   - **Features**: Draft re-engagement campaign

---

### Email Automations (3 automations)

1. **Welcome Series**
   - **Type**: Drip
   - **Status**: Active
   - **Trigger**: EventBusEvent-based (`user_registered`)
   - **Entry Segment**: VIP Customers
   - **Workflow Steps**:
     1. Send welcome email (immediate)
     2. Wait 2 days
     3. Send getting started guide
   - **Features**: Multi-step drip sequence

2. **Re-engagement Campaign**
   - **Type**: Custom
   - **Status**: Active
   - **Trigger**: EventBusEvent-based (`email_not_opened` with condition: `days_since_last_open > 30`)
   - **Entry Segment**: Inactive Subscribers
   - **Workflow Steps**:
     1. Send re-engagement email
   - **Features**: Behavioral trigger automation

3. **Abandoned Cart Recovery**
   - **Type**: Custom
   - **Status**: Active
   - **Trigger**: EventBusEvent-based (`cart_abandoned` with condition: `cart_value > 50`)
   - **Entry Segment**: Recent Purchasers
   - **Workflow Steps**:
     1. Wait 1 hour
     2. Send abandoned cart email
   - **Features**: Time-delayed automation

---

## Demo Data Usage Examples

### 1. View Campaign Performance

**Navigation**: Email Marketing → Campaigns → "Welcome Email Series"

**What to See**:
- Campaign metrics (sent, delivered, opened, clicked)
- Open rate: 37.5%
- Click rate: 15%
- Bounce rate: 4%
- Campaign timeline and activity

**Demo Purpose**: Shows completed campaign with real metrics

---

### 2. Create New Campaign

**Navigation**: Email Marketing → Campaigns → Create Campaign

**Steps**:
1. Select template: "Newsletter Template"
2. Choose segment: "Newsletter Subscribers"
3. Customize subject line
4. Preview email
5. Schedule or send immediately

**Demo Purpose**: Demonstrates campaign creation workflow

---

### 3. View Scheduled Campaign

**Navigation**: Email Marketing → Campaigns → "Product Launch Announcement"

**What to See**:
- Campaign scheduled for 2 days from now
- Segment selected
- Template assigned
- Ability to edit before sending

**Demo Purpose**: Shows scheduled campaign management

---

### 4. Explore Email Segments

**Navigation**: Email Marketing → Segments

**What to See**:
- 4 different segment types (Static, Dynamic, Behavioral)
- Segment criteria and member counts
- Ability to create new segments

**Demo Purpose**: Demonstrates segmentation capabilities

---

### 5. View Email Automations

**Navigation**: Email Marketing → Automations

**What to See**:
- 3 active automations
- Workflow definitions
- Trigger configurations
- Enrollment statistics

**Demo Purpose**: Shows automation workflow capabilities

---

### 6. Test AI Agents

**Navigation**: AI Agent Management → Email Marketing Agents

**Available Agents**:
1. `email_send_time_optimizer` - Optimize send times
2. `email_subject_line_generator` - Generate subject lines
3. `email_content_personalizer` - Personalize content
4. `email_engagement_predictor` - Predict engagement

**Demo Purpose**: Demonstrates AI-powered email optimization

---

### 7. Test Workflows

**Navigation**: Workflow Automation → Email Marketing Workflows

**Available Workflows**:
1. `email_campaign_send` - Campaign send workflow
2. `automation_trigger` - Automation trigger workflow

**Demo Purpose**: Shows workflow automation integration

---

### 8. Test Ask Amani Integration

**Example Prompts**:
- "Create an email campaign for a new product launch"
- "Optimize the subject line for the welcome email campaign"
- "Show me underperforming campaigns"
- "Draft a product launch email"

**Demo Purpose**: Demonstrates natural language campaign creation

---

## Resetting Demo Data

### Option 1: Delete and Re-seed

```bash
# Connect to database
psql $POSTGRES_CONNECTION_STRING

# Delete existing demo data (for demo tenant)
DELETE FROM email_campaigns WHERE tenant_id = (SELECT id FROM tenants WHERE domain = 'saraise.com');
DELETE FROM email_segments WHERE tenant_id = (SELECT id FROM tenants WHERE domain = 'saraise.com');
DELETE FROM email_automations WHERE tenant_id = (SELECT id FROM tenants WHERE domain = 'saraise.com');
DELETE FROM email_templates WHERE tenant_id = (SELECT id FROM tenants WHERE domain = 'saraise.com');

# Re-run seeder
cd backend
python scripts/seed_email_marketing_demo.py
```

### Option 2: Re-run Seeder (Idempotent)

The seeder script is idempotent - it checks for existing data and skips if found. To force re-seeding:

1. Delete existing data (see Option 1)
2. Run seeder: `python scripts/seed_email_marketing_demo.py`

---

## Demo Data Safety

### Anonymized Data

All demo data uses:
- Generic email addresses (e.g., `user@example.com`)
- Fictional company names
- Anonymized personal information
- Safe test data only

### No Real Email Sending

Demo campaigns are configured with:
- Test email addresses
- No actual SMTP configuration
- Safe test mode enabled

### Data Isolation

All demo data is:
- Tenant-isolated (Demo Tenant only)
- Not accessible to other tenants
- Safe for production-like testing

---

## Demo Data Coverage

### Features Demonstrated

✅ **Campaign Management**
- Create, read, update, delete campaigns
- Campaign scheduling
- Status management (draft, scheduled, sending, sent)
- Campaign metrics and analytics

✅ **Segmentation**
- Static segments
- Dynamic segments
- Behavioral segments
- Segment criteria configuration

✅ **Templates**
- HTML templates
- Text templates
- Personalization variables
- Template versioning

✅ **Automation**
- Drip sequences
- EventBusEvent-based triggers
- Behavioral triggers
- Multi-step workflows

✅ **AI Agents**
- Send time optimization
- Subject line generation
- Content personalization
- Engagement prediction

✅ **Workflows**
- Campaign send workflow
- Automation trigger workflow

✅ **Analytics**
- Campaign performance metrics
- Open/click rates
- Bounce rates
- Engagement tracking

---

## Demo Data Limitations

### Not Included

- Real subscriber email addresses (for privacy)
- Actual email sending (requires SMTP configuration)
- Real-time webhook events (requires external setup)
- Integration with external email providers (requires API keys)

### Safe for Production

All demo data is safe to use in production environments:
- No real email addresses
- No actual email sending
- No external API calls
- Fully tenant-isolated

---

## Troubleshooting

### Demo Data Not Visible

**Issue**: Demo data not showing in UI

**Solutions**:
1. Verify you're logged in as `demo@saraise.com`
2. Check tenant is "Demo Tenant"
3. Verify module is installed for tenant
4. Check database connection
5. Re-run seeder: `python scripts/seed_email_marketing_demo.py`

### Campaign Metrics Not Updating

**Issue**: Campaign metrics showing zero

**Solutions**:
1. Metrics are pre-populated in demo data
2. Real metrics require actual email sending
3. Check campaign status (must be "sent" or "sending")
4. Verify email service is configured

### Automation Not Triggering

**Issue**: Automation not executing

**Solutions**:
1. Verify automation status is "active"
2. Check trigger conditions are met
3. Verify entry segment has members
4. Check automation workflow definition
5. Review automation logs

---

## Next Steps

After exploring demo data:

1. **Create Your Own Campaign**: Use templates and segments to create a new campaign
2. **Test AI Agents**: Try optimizing send times or generating subject lines
3. **Set Up Automation**: Create a new automation workflow
4. **Explore Integrations**: Test CRM, Marketing Analytics, and other integrations
5. **Customize Templates**: Edit templates and add personalization variables

---

## References

- [Email Marketing Module README](./README.md)
- [Email Marketing Customization Guide](./CUSTOMIZATION.md)
- [Email Marketing Integrations](./INTEGRATIONS.md)
- [Email Marketing Agent Configuration](./AGENT-CONFIGURATION.md)

---

**Last Updated**: 2025-01-XX
**Version**: 1.0.0

## Troubleshooting

<!-- TODO: Add troubleshooting guide -->
