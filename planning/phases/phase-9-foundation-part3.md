# Phase 9: Foundation Modules Part 3 — Advanced Foundation

**Duration:** 5 weeks (Weeks 11-15)  
**Modules:** Billing & Subscriptions, Data Migration, AI Provider Configuration, Localization  
**Status:** 🟡 PENDING (Blocked on Phase 8)  
**Prerequisites:** Phase 8 complete

---

## Phase Objectives

Complete Foundation module layer with billing, data migration, AI infrastructure, and internationalization.

### Success Criteria
- [ ] 4 modules operational (backend + frontend + tests)
- [ ] ≥90% test coverage per module
- [ ] Platform ready for Core business modules

---

## Week 11-12: Billing & Subscriptions Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `billing_subscriptions` |
| Type | Foundation |
| Priority | P1 |
| Dependencies | Tenant Management |
| Spec Location | `docs/modules/01-foundation/billing-subscriptions/` |
| Timeline | 7-10 days |

### Key Entities

```python
# Billing entities
- SubscriptionPlan (name, price, billing_cycle, features, limits)
- Subscription (tenant_id, plan_id, status, start_date, end_date)
- Invoice (tenant_id, subscription_id, amount, status, due_date)
- InvoiceLineItem (invoice_id, description, quantity, unit_price)
- Payment (invoice_id, amount, method, status, transaction_id)
- UsageRecord (tenant_id, resource_type, quantity, recorded_at)
```

### API Endpoints

```
# Plans
GET /api/v1/billing/plans/
GET /api/v1/billing/plans/{id}/

# Subscriptions
GET /api/v1/billing/subscriptions/
POST /api/v1/billing/subscriptions/
PUT /api/v1/billing/subscriptions/{id}/
POST /api/v1/billing/subscriptions/{id}/cancel/
POST /api/v1/billing/subscriptions/{id}/upgrade/

# Invoices
GET /api/v1/billing/invoices/
GET /api/v1/billing/invoices/{id}/
GET /api/v1/billing/invoices/{id}/pdf/

# Payments
POST /api/v1/billing/payments/
GET /api/v1/billing/payments/{id}/

# Usage
GET /api/v1/billing/usage/
POST /api/v1/billing/usage/record/
```

### Key Implementation: Subscription Lifecycle

```python
# backend/src/modules/billing_subscriptions/services.py

class SubscriptionService:
    """Manages subscription lifecycle."""

    def create_subscription(
        self,
        tenant_id: uuid.UUID,
        plan_id: uuid.UUID,
        payment_method_id: str
    ) -> Subscription:
        """Create new subscription for tenant."""

        plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)

        # Check for existing active subscription
        existing = Subscription.objects.filter(
            tenant_id=tenant_id,
            status__in=['active', 'trialing']
        ).first()

        if existing:
            raise ValueError("Tenant already has active subscription")

        subscription = Subscription.objects.create(
            tenant_id=tenant_id,
            plan=plan,
            status='pending',
            start_date=timezone.now(),
            billing_cycle_anchor=timezone.now()
        )

        # Create initial invoice
        invoice = self._create_invoice(subscription)

        # Process payment
        payment_result = self._process_payment(invoice, payment_method_id)

        if payment_result.success:
            subscription.status = 'active'
            subscription.save()

            # Update tenant quotas based on plan
            self._update_tenant_quotas(tenant_id, plan)

        return subscription

    def upgrade_subscription(
        self,
        tenant_id: uuid.UUID,
        new_plan_id: uuid.UUID
    ) -> Subscription:
        """Upgrade subscription to new plan."""

        subscription = Subscription.objects.get(
            tenant_id=tenant_id,
            status='active'
        )
        old_plan = subscription.plan
        new_plan = SubscriptionPlan.objects.get(id=new_plan_id)

        # Calculate prorated amount
        proration = self._calculate_proration(subscription, new_plan)

        # Update subscription
        subscription.plan = new_plan
        subscription.save()

        # Update tenant quotas
        self._update_tenant_quotas(tenant_id, new_plan)

        # Create prorated invoice if needed
        if proration > 0:
            self._create_proration_invoice(subscription, proration)

        return subscription
```

---

## Week 12-13: Data Migration Framework Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `data_migration` |
| Type | Foundation |
| Priority | P1 |
| Dependencies | Metadata Modeling |
| Spec Location | `docs/modules/01-foundation/data-migration/` |
| Timeline | 5-7 days |

### Key Entities

```python
# Migration entities
- MigrationJob (name, source_type, status, tenant_id)
- MigrationMapping (job_id, source_field, target_field, transform)
- MigrationLog (job_id, level, message, timestamp)
- MigrationValidation (job_id, field, rule, status)
- MigrationRollback (job_id, checkpoint_data, created_at)
```

### Key Implementation: Migration Engine

```python
# backend/src/modules/data_migration/services.py

class MigrationEngine:
    """Handles data import/migration with validation and rollback."""

    def execute_migration(
        self,
        job_id: uuid.UUID,
        tenant_id: uuid.UUID,
        dry_run: bool = False
    ) -> MigrationResult:
        """Execute migration job."""

        job = MigrationJob.objects.get(
            id=job_id,
            tenant_id=tenant_id  # TENANT ISOLATION
        )

        # Create checkpoint for rollback
        checkpoint = self._create_checkpoint(job) if not dry_run else None

        results = {
            'processed': 0,
            'succeeded': 0,
            'failed': 0,
            'errors': []
        }

        try:
            # Load source data
            source_data = self._load_source_data(job)

            for record in source_data:
                results['processed'] += 1

                try:
                    # Apply field mappings
                    transformed = self._apply_mappings(job, record)

                    # Validate
                    validation_errors = self._validate_record(job, transformed)

                    if validation_errors:
                        results['failed'] += 1
                        results['errors'].extend(validation_errors)
                        continue

                    # Import if not dry run
                    if not dry_run:
                        self._import_record(job, transformed, tenant_id)

                    results['succeeded'] += 1

                except Exception as e:
                    results['failed'] += 1
                    results['errors'].append(str(e))
                    self._log_error(job, record, str(e))

            job.status = 'completed' if results['failed'] == 0 else 'completed_with_errors'
            job.save()

        except Exception as e:
            job.status = 'failed'
            job.save()

            # Rollback if needed
            if checkpoint and not dry_run:
                self._rollback(checkpoint)

            raise

        return MigrationResult(**results)
```

---

## Week 13-14: AI Provider Configuration Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `ai_provider_configuration` |
| Type | Foundation |
| Priority | P1 |
| Dependencies | Security, Platform Management |
| Spec Location | `docs/modules/01-foundation/ai-provider-configuration/` |
| Timeline | 5-7 days |

### Key Entities

```python
# AI Provider entities
- AIProvider (name, provider_type, base_url, is_active)
- AIProviderCredential (provider_id, tenant_id, api_key_encrypted)
- AIModel (provider_id, model_id, capabilities, pricing)
- AIModelDeployment (model_id, tenant_id, config, status)
- AIUsageLog (deployment_id, tenant_id, tokens_used, cost, timestamp)
```

### Key Implementation: Provider Abstraction

```python
# backend/src/modules/ai_provider_configuration/services.py

from abc import ABC, abstractmethod
from typing import Optional
import openai
import anthropic


class AIProviderService(ABC):
    """Abstract base for AI provider integration."""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> str:
        pass


class OpenAIProvider(AIProviderService):
    """OpenAI provider implementation."""

    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)

    def complete(
        self,
        prompt: str,
        model: str = "gpt-4",
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> str:
        response = self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content


class AnthropicProvider(AIProviderService):
    """Anthropic Claude provider implementation."""

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        prompt: str,
        model: str = "claude-3-opus-20240229",
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> str:
        response = self.client.messages.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.content[0].text


class AIProviderFactory:
    """Factory for creating provider instances."""

    @staticmethod
    def get_provider(
        provider_type: str,
        tenant_id: uuid.UUID
    ) -> AIProviderService:
        """Get provider instance for tenant."""

        credential = AIProviderCredential.objects.get(
            provider__provider_type=provider_type,
            tenant_id=tenant_id
        )

        api_key = decrypt_api_key(credential.api_key_encrypted)

        if provider_type == 'openai':
            return OpenAIProvider(api_key)
        elif provider_type == 'anthropic':
            return AnthropicProvider(api_key)
        else:
            raise ValueError(f"Unknown provider: {provider_type}")
```

---

## Week 14-15: Localization Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `localization` |
| Type | Foundation |
| Priority | P2 |
| Dependencies | Tenant Management |
| Spec Location | `docs/modules/01-foundation/localization/` |
| Timeline | 5-7 days |

### Key Entities

```python
# Localization entities
- Language (code, name, native_name, is_rtl, is_active)
- Translation (language_id, key, value, context)
- LocaleConfig (tenant_id, default_language, timezone, date_format)
- CurrencyConfig (tenant_id, default_currency, exchange_rates)
- RegionalSettings (tenant_id, country_code, tax_settings)
```

### Key Implementation: Translation Service

```python
# backend/src/modules/localization/services.py

class TranslationService:
    """Handles multi-language translations."""

    _cache = {}

    def translate(
        self,
        key: str,
        language_code: str,
        default: str = None,
        context: str = None
    ) -> str:
        """Get translation for key."""

        cache_key = f"{language_code}:{key}:{context or ''}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        translation = Translation.objects.filter(
            language__code=language_code,
            key=key
        )

        if context:
            translation = translation.filter(context=context)

        translation = translation.first()

        if translation:
            self._cache[cache_key] = translation.value
            return translation.value

        return default or key

    def get_tenant_locale(self, tenant_id: uuid.UUID) -> LocaleConfig:
        """Get locale configuration for tenant."""

        config = LocaleConfig.objects.filter(tenant_id=tenant_id).first()

        if not config:
            # Return default config
            return LocaleConfig(
                default_language='en',
                timezone='UTC',
                date_format='YYYY-MM-DD'
            )

        return config
```

---

## Phase Completion Criteria

### Mandatory Checkpoints

- [ ] 4 modules operational (backend + frontend)
- [ ] ≥90% test coverage per module
- [ ] All pre-commit hooks passing
- [ ] Billing integration tested
- [ ] AI provider integration tested
- [ ] Multi-language support verified

### Foundation Milestone

At end of Phase 9, Foundation layer is COMPLETE:
- ✅ Platform Management
- ✅ Tenant Management
- ✅ Security & Access Control
- ✅ Workflow Automation
- ✅ Metadata Modeling
- ✅ Document Management
- ✅ Integration Platform
- ✅ Billing & Subscriptions
- ✅ Data Migration
- ✅ AI Provider Configuration
- ✅ Localization

**Total Foundation Modules:** 11 operational (+ AI Agent Management from Phase 6)

---

## Document Status

**Status:** PENDING (Blocked on Phase 8)  
**Last Updated:** January 5, 2026  
**Next Phase:** Phase 10 (CRM, Accounting)

---

