<!-- SPDX-License-Identifier: Apache-2.0 -->
# AI Provider Configuration Module

**Module Code**: `ai_provider_configuration`
**Category**: AI & Automation
**Priority**: Critical - Foundation for all AI features
**Version**: 1.0.0
**Status**: Planning Phase

---

## Executive Summary

The AI Provider Configuration module provides a **unified interface** for integrating and managing multiple Large Language Model (LLM) providers. This module is the foundational layer that enables SARAISE's AI-first architecture, allowing seamless switching between providers, cost optimization, and failover resilience.

###

 Key Objectives

1. **Provider Agnostic**: Single API for all LLM providers
2. **Cost Optimization**: Automatic routing to cheapest provider for each task
3. **Resilience**: Automatic failover on provider failures
4. **Governance**: Complete audit trail of AI usage and costs
5. **Flexibility**: Easy addition of new providers
6. **Security**: Secure API key management with encryption

---

## World-Class Features

### Core Capabilities

#### 1. Multi-Provider Support
**Status**: Must-Have | **Competitive Parity**: Industry Leading

Support for **30+ LLM providers** across multiple tiers:

**Tier 1 - Enterprise Providers**
- OpenAI (GPT-4, GPT-3.5-turbo, GPT-4-turbo, o1-preview, o1-mini)
- Anthropic (Claude 3 Opus, Sonnet, Haiku, Claude 3.5)
- Google (Gemini 1.5 Pro, Gemini 1.0 Pro, PaLM 2)
- Microsoft Azure OpenAI (All Azure-hosted OpenAI models)
- AWS Bedrock (Claude, Titan, Llama 2 on AWS)

**Tier 2 - Specialized Providers**
- Groq (Llama 3, Mixtral) - Ultra-fast inference
- Cohere (Command, Command-R) - Enterprise RAG
- Mistral AI (Mistral Large, Medium, Small) - European AI
- Perplexity (pplx-7b, pplx-70b) - Search-augmented
- xAI (Grok) - Real-time knowledge

**Tier 3 - Cost-Effective Providers**
- DeepSeek (DeepSeek-Chat, DeepSeek-Coder)
- Together AI (Open-source models)
- Fireworks AI (Production inference)
- Replicate (Model marketplace)
- Hugging Face (Community models)

**Tier 4 - Self-Hosted Options**
- Ollama (Local deployment)
- LM Studio (Desktop models)
- LocalAI (OpenAI-compatible)
- vLLM (High-throughput)
- Text Generation Inference (HuggingFace)

**Comparison**: Most ERP systems support 1-3 providers. We support 30+.

#### 2. Unified API Interface
**Status**: Must-Have | **Competitive Advantage**: Unique

```python
# Single interface for all providers
response = await ai_provider.complete(
    prompt="Analyze this sales data",
    model="gpt-4",  # Or "claude-3-opus", "gemini-pro"
    provider="openai",  # Auto-selected if not specified
    temperature=0.7,
    max_tokens=1000
)
```

**Features**:
- Unified request/response format
- Automatic parameter translation per provider
- Streaming support across all providers
- Batch processing capabilities

**Comparison**: Competitors require provider-specific code. We provide complete abstraction.

#### 3. Intelligent Provider Routing
**Status**: Must-Have | **Competitive Advantage**: Industry Leading

**Routing Strategies**:
1. **Cost-Optimized**: Route to cheapest provider meeting quality requirements
2. **Performance-Optimized**: Route to fastest provider
3. **Quality-Optimized**: Route to highest quality provider
4. **Load-Balanced**: Distribute across multiple providers
5. **Failover**: Automatic fallback on provider failure
6. **Geo-Aware**: Route to geographically closest provider

**Configuration**:
```python
routing_config = {
    "strategy": "cost_optimized",
    "quality_threshold": 0.85,  # Minimum quality score
    "max_latency": 2000,  # Max 2 second response
    "preferred_providers": ["openai", "anthropic"],
    "fallback_chain": ["groq", "together_ai"]
}
```

**Comparison**: No competitor offers intelligent routing. Huge cost savings potential.

#### 4. Cost Management & Optimization
**Status**: Must-Have | **Competitive Advantage**: Unique

**Cost Tracking**:
- Real-time cost tracking per request
- Daily/monthly budget limits per provider
- Cost alerts and notifications
- Historical cost analysis
- Cost attribution by tenant, user, module

**Cost Optimization**:
- Automatic provider switching based on cost
- Caching of repeated requests
- Prompt compression to reduce tokens
- Batch processing for efficiency
- Smart model selection (use GPT-3.5 for simple tasks, GPT-4 for complex)

**Budget Controls**:
```python
budget_config = {
    "monthly_limit": 10000,  # $10,000/month
    "daily_limit": 500,      # $500/day
    "per_user_limit": 100,   # $100/user/month
    "alert_threshold": 0.80, # Alert at 80% usage
    "auto_cutoff": True      # Stop at limit
}
```

**Comparison**: Basic cost tracking exists in some platforms. Our optimization is industry-first.

#### 5. Provider Health Monitoring
**Status**: Must-Have | **Competitive Parity**: Advanced

**Monitoring Metrics**:
- Response time (p50, p95, p99)
- Error rates
- Token usage
- API rate limits
- Cost per request
- Quality scores

**Health Checks**:
- Automatic provider health checks every 60 seconds
- Real-time status dashboard
- Historical uptime tracking
- Incident management

**Alerting**:
- Provider downtime alerts
- Performance degradation warnings
- Rate limit approaching notifications
- Cost spike alerts

#### 6. Secure API Key Management
**Status**: Must-Have | **Compliance Requirement**: SOC2, ISO 27001

**Security Features**:
- AES-256-GCM encryption for API keys at rest
- Secure key rotation
- Access control per provider
- Audit logging of key usage
- Integration with HashiCorp Vault
- Support for environment variables

**Key Hierarchy**:
1. **Platform-Level Keys**: Default keys for all tenants
2. **Tenant-Level Keys**: Tenant-specific keys (BYOK - Bring Your Own Key)
3. **User-Level Keys**: User-specific keys for personal usage

#### 7. Rate Limit Management
**Status**: Must-Have | **Competitive Parity**: Industry Standard

**Rate Limiting**:
- Per-provider rate limits
- Per-tenant rate limits
- Per-user rate limits
- Per-module rate limits
- Automatic throttling
- Queue management for excess requests

**Rate Limit Strategies**:
- Token bucket algorithm
- Leaky bucket algorithm
- Fixed window
- Sliding window

#### 8. Response Caching
**Status**: Should-Have | **Competitive Advantage**: Advanced

**Caching Strategy**:
- Semantic caching (similar prompts return cached responses)
- Exact match caching
- TTL-based expiration
- Cache warming for common queries
- Multi-level cache (Redis L1, PostgreSQL L2)

**Cache Configuration**:
```python
cache_config = {
    "enabled": True,
    "ttl": 3600,  # 1 hour
    "semantic_similarity_threshold": 0.95,
    "max_cache_size": "10GB"
}
```

**Benefits**:
- 80% cost reduction for repeated queries
- 10x faster response times
- Reduced provider load

#### 9. Model Version Management
**Status**: Should-Have | **Competitive Advantage**: Unique

**Capabilities**:
- Track model versions per provider
- A/B testing between models
- Gradual rollout of new models
- Rollback to previous models
- Model performance comparison

**Version Control**:
```python
model_config = {
    "production": "gpt-4-turbo-2024-04-09",
    "canary": "gpt-4-turbo-2024-11-01",  # 10% traffic
    "rollback": "gpt-4-1106-preview"
}
```

#### 10. Prompt Management
**Status**: Should-Have | **Competitive Advantage**: Advanced

**Prompt Library**:
- Centralized prompt templates
- Version control for prompts
- A/B testing of prompts
- Prompt optimization suggestions
- Multi-language prompt support

**Prompt Engineering**:
- Few-shot learning templates
- Chain-of-thought templates
- ReAct pattern templates
- Automatic prompt optimization

---

## Technical Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                 API Layer (Django REST Framework)           │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐  │
│  │   CRM    │   AI     │ Support  │Workflow  │  Other   │  │
│  │  Module  │  Agent   │  Desk    │ Engine   │ Modules  │  │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              AI Provider Orchestration Layer                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Provider Router  │  Cost Optimizer  │  Cache Layer  │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │   Rate Limiter    │  Health Monitor  │ Failover Mgr  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│   Provider     │  │   Provider     │  │   Provider     │
│   Adapters     │  │   Adapters     │  │   Adapters     │
│                │  │                │  │                │
│ - OpenAI      │  │ - Anthropic    │  │ - Self-Hosted  │
│ - Google      │  │ - Mistral      │  │ - Ollama       │
│ - Azure       │  │ - Groq         │  │ - vLLM         │
└────────────────┘  └────────────────┘  └────────────────┘
```

### Database Schema

```sql
-- Provider Configuration
CREATE TABLE ai_providers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),  -- NULL for platform-level
    provider_name VARCHAR(100) NOT NULL,    -- 'openai', 'anthropic', etc.
    provider_type VARCHAR(50) NOT NULL,     -- 'cloud', 'self_hosted'
    enabled BOOLEAN DEFAULT true,

    -- Configuration
    config JSONB NOT NULL,  -- Provider-specific config
    api_key_encrypted TEXT,  -- AES-256 encrypted
    api_endpoint TEXT,       -- Custom endpoint (for self-hosted)

    -- Limits
    rate_limit_per_minute INTEGER,
    rate_limit_per_day INTEGER,
    monthly_budget_limit DECIMAL(10, 2),
    daily_budget_limit DECIMAL(10, 2),

    -- Status
    status VARCHAR(50) DEFAULT 'active',  -- active, disabled, error
    last_health_check TIMESTAMPTZ,
    health_status VARCHAR(50),  -- healthy, degraded, down

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    UNIQUE(tenant_id, provider_name)
);

-- Model Configuration
CREATE TABLE ai_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id UUID REFERENCES ai_providers(id),
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50),

    -- Capabilities
    supports_streaming BOOLEAN DEFAULT false,
    supports_function_calling BOOLEAN DEFAULT false,
    max_tokens INTEGER,
    max_context_window INTEGER,

    -- Pricing
    cost_per_1k_input_tokens DECIMAL(10, 6),
    cost_per_1k_output_tokens DECIMAL(10, 6),

    -- Performance
    avg_latency_ms INTEGER,
    avg_quality_score DECIMAL(3, 2),

    -- Status
    enabled BOOLEAN DEFAULT true,
    deprecated BOOLEAN DEFAULT false,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(provider_id, model_name, model_version)
);

-- Request Logs
CREATE TABLE ai_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    user_id UUID REFERENCES users(id),
    module_name VARCHAR(100),  -- Which module made the request

    -- Provider Details
    provider_id UUID REFERENCES ai_providers(id),
    model_id UUID REFERENCES ai_models(id),
    model_name VARCHAR(100),

    -- Request Details
    prompt_hash VARCHAR(64),  -- SHA-256 hash for caching
    prompt_text TEXT,  -- Optional, for debugging
    completion_text TEXT,  -- Optional, for debugging

    -- Tokens
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,

    -- Performance
    latency_ms INTEGER,
    cache_hit BOOLEAN DEFAULT false,

    -- Cost
    cost_usd DECIMAL(10, 6),

    -- Status
    status VARCHAR(50),  -- success, error, timeout
    error_message TEXT,

    -- Timing
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Indexes for analytics
    INDEX idx_tenant_created (tenant_id, created_at),
    INDEX idx_provider_created (provider_id, created_at),
    INDEX idx_module_created (module_name, created_at),
    INDEX idx_prompt_hash (prompt_hash)
);

-- Cache Table
CREATE TABLE ai_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_hash VARCHAR(64) UNIQUE NOT NULL,
    prompt_text TEXT,

    -- Response
    completion_text TEXT NOT NULL,
    model_name VARCHAR(100),

    -- Metadata
    hits INTEGER DEFAULT 0,
    last_accessed TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_hash_expiry (prompt_hash, expires_at)
);

-- Budget Tracking
CREATE TABLE ai_budget_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    provider_id UUID REFERENCES ai_providers(id),

    -- Period
    period_type VARCHAR(20),  -- 'daily', 'monthly'
    period_start DATE,
    period_end DATE,

    -- Usage
    total_requests INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost DECIMAL(10, 2) DEFAULT 0,

    -- Limits
    budget_limit DECIMAL(10, 2),
    budget_remaining DECIMAL(10, 2),
    limit_reached BOOLEAN DEFAULT false,

    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(tenant_id, provider_id, period_type, period_start)
);
```

### API Endpoints

```python
# Provider Management
POST   /api/v1/ai-providers/              # Create provider config
GET    /api/v1/ai-providers/              # List providers
GET    /api/v1/ai-providers/{id}          # Get provider details
PUT    /api/v1/ai-providers/{id}          # Update provider
DELETE /api/v1/ai-providers/{id}          # Delete provider
POST   /api/v1/ai-providers/{id}/test     # Test provider connection

# Model Management
GET    /api/v1/ai-providers/{id}/models   # List available models
POST   /api/v1/ai-providers/{id}/models   # Add/enable model
PUT    /api/v1/ai-models/{id}             # Update model config

# Completion API (Unified Interface)
POST   /api/v1/ai/complete                # Text completion
POST   /api/v1/ai/stream                  # Streaming completion
POST   /api/v1/ai/embed                   # Generate embeddings
POST   /api/v1/ai/moderate                # Content moderation

# Analytics
GET    /api/v1/ai/usage                   # Usage statistics
GET    /api/v1/ai/costs                   # Cost breakdown
GET    /api/v1/ai/performance             # Performance metrics
GET    /api/v1/ai/health                  # Provider health status

# Budget Management
GET    /api/v1/ai/budget                  # Current budget status
POST   /api/v1/ai/budget                  # Set budget limits
GET    /api/v1/ai/budget/alerts           # Budget alerts

# Cache Management
GET    /api/v1/ai/cache/stats             # Cache statistics
DELETE /api/v1/ai/cache                   # Clear cache
POST   /api/v1/ai/cache/warm              # Warm cache with common queries
```

---

## Data Models

### Provider Configuration Schema (Django Serializer)

```python
from rest_framework import serializers
from typing import Optional, Dict, Any, List
from enum import Enum

class ProviderType(str, Enum):
    CLOUD = "cloud"
    SELF_HOSTED = "self_hosted"

class ProviderStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"

class ProviderCreate(BaseModel):
    provider_name: str = Field(..., min_length=1, max_length=100)
    provider_type: ProviderType
    api_key: Optional[SecretStr] = None
    api_endpoint: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    rate_limit_per_minute: Optional[int] = Field(None, ge=1)
    monthly_budget_limit: Optional[float] = Field(None, ge=0)

class ProviderResponse(BaseModel):
    id: str
    provider_name: str
    provider_type: ProviderType
    enabled: bool
    status: ProviderStatus
    health_status: Optional[str]
    last_health_check: Optional[datetime]
    config: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True
```

### Completion Request Schema

```python
class CompletionRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    model: Optional[str] = "gpt-3.5-turbo"
    provider: Optional[str] = None  # Auto-select if None
    temperature: float = Field(0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(None, ge=1)
    top_p: Optional[float] = Field(1.0, ge=0, le=1)
    stream: bool = False
    functions: Optional[List[Dict]] = None

    # Routing preferences
    routing_strategy: Optional[str] = "cost_optimized"
    quality_threshold: Optional[float] = Field(0.8, ge=0, le=1)
    max_latency_ms: Optional[int] = Field(5000, ge=100)

class CompletionResponse(BaseModel):
    id: str
    completion: str
    model: str
    provider: str
    tokens_used: int
    cost_usd: float
    latency_ms: int
    cached: bool
    created_at: datetime
```

---

## AI Agent Integration

### Configuration Agent

**Role**: Manages provider configuration for tenants

**Capabilities**:
1. **Auto-Configure Providers**: Automatically set up providers based on tenant subscription
2. **Cost Optimization**: Recommend optimal provider mix based on usage patterns
3. **Health Monitoring**: Proactively detect and resolve provider issues
4. **Usage Analysis**: Analyze usage and suggest improvements

**Governance**:
- Changes to production provider config require approval
- Budget limit changes require admin approval
- API key rotation requires MFA

**Example Workflow**:
```
User: "Configure OpenAI for our tenant"
Agent: "I'll set up OpenAI for you. I need your API key."
User: [Provides API key]
Agent: "API key received. Testing connection... ✓ Success!
       Default budget: $1000/month. Would you like to adjust?"
User: "Set it to $500/month"
Agent: "Budget set to $500/month. Alerts configured at $400 (80%).
       Configuration complete. OpenAI is now available."
```

### Support Agent

**Role**: Helps users troubleshoot provider issues

**Capabilities**:
1. **Diagnose Connection Issues**: Test provider connectivity
2. **Explain Errors**: Translate technical errors into user-friendly language
3. **Suggest Solutions**: Recommend fixes for common issues
4. **Escalate Complex Issues**: Escalate to human support when needed

---

## Implementation Roadmap

### Phase 1: Core Infrastructure (Month 1)
- [ ] Database schema implementation
- [ ] Provider adapter framework
- [ ] OpenAI, Anthropic, Google adapters
- [ ] Basic routing logic
- [ ] API key encryption
- [ ] Simple caching

### Phase 2: Advanced Features (Month 2)
- [ ] Intelligent routing strategies
- [ ] Cost optimization engine
- [ ] Health monitoring system
- [ ] Rate limiting
- [ ] Budget management
- [ ] Semantic caching

### Phase 3: Additional Providers (Month 3)
- [ ] Groq, Mistral, Cohere adapters
- [ ] Self-hosted provider support (Ollama, vLLM)
- [ ] Provider marketplace
- [ ] A/B testing framework

### Phase 4: AI Agent Integration (Month 4)
- [ ] Configuration agent
- [ ] Support agent
- [ ] Auto-optimization agent
- [ ] Governance framework

---

## Testing Strategy

### Unit Tests
- Provider adapter tests (95%+ coverage)
- Routing logic tests
- Cost calculation tests
- Cache hit/miss tests

### Integration Tests
- End-to-end provider communication
- Failover scenarios
- Rate limiting
- Budget enforcement

### Performance Tests
- Load testing with 10,000 concurrent requests
- Latency benchmarks < 100ms overhead
- Cache hit rate > 80%

### Security Tests
- API key encryption/decryption
- Access control tests
- Rate limit bypass attempts
- SQL injection tests

---

## Competitive Analysis

| Feature | SARAISE | SAP | Oracle | Odoo | Dynamics 365 |
|---------|---------|-----|--------|------|--------------|
| **Provider Count** | 30+ | 1 (Azure) | 2 | 1 (OpenAI) | 2 (Azure) |
| **Intelligent Routing** | ✓ | ✗ | ✗ | ✗ | ✗ |
| **Cost Optimization** | ✓ | ✗ | ✗ | ✗ | ✗ |
| **Automatic Failover** | ✓ | ✗ | ✗ | ✗ | Partial |
| **Semantic Caching** | ✓ | ✗ | ✗ | ✗ | ✗ |
| **Self-Hosted Support** | ✓ | ✗ | ✗ | ✗ | ✗ |
| **Real-Time Monitoring** | ✓ | ✓ | ✓ | Partial | ✓ |
| **Budget Management** | ✓ | Basic | Basic | ✗ | Basic |

**Verdict**: Industry-leading. No competitor comes close to our breadth and depth.

---

## Success Metrics

### Technical KPIs
- **API Response Time**: < 100ms overhead (excluding provider latency)
- **Cache Hit Rate**: > 80% for repeated queries
- **Provider Uptime**: > 99.9% (via failover)
- **Cost Reduction**: 40% reduction via optimization

### Business KPIs
- **Tenant Adoption**: 95% of tenants use AI features
- **Cost Savings**: Average $2000/month per tenant
- **User Satisfaction**: 4.5+ rating for AI features
- **Support Tickets**: < 5% related to provider issues

---

## Security & Compliance

### Data Protection
- API keys encrypted at rest (AES-256-GCM)
- API keys in transit (TLS 1.3)
- No storage of sensitive prompt data (configurable)
- GDPR-compliant data retention

### Access Control
- Role-based access to provider configuration
- MFA required for API key changes
- Audit logging of all provider operations

### Compliance
- SOC 2 Type II certified
- GDPR compliant
- HIPAA compliant (for healthcare module)
- ISO 27001 certified

---

## Dependencies

### Required Modules
- **Platform Management**: System configuration
- **Tenant Management**: Multi-tenant isolation
- **Billing & Subscriptions**: Usage-based billing for AI

### Optional Modules
- **AI Agent Management**: Enhanced with provider configuration
- **Workflow Automation**: Uses AI providers
- **Analytics**: Cost and usage analytics

---

## References

### External Documentation
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference)
- [Anthropic Claude API](https://docs.anthropic.com/claude/reference)
- [Google Gemini API](https://ai.google.dev/docs)
- [LiteLLM Documentation](https://docs.litellm.ai/)

### Internal Documentation
- Module Architecture: `docs/architecture/02-module-architecture.md`
- AI Agent Management: `docs/modules/03-ai-automation/AI-AGENT-MANAGEMENT.md`
- Security Standards: `.cursor/rules/15-secrets-management.mdc`

---

**Document Control**:
- **Author**: SARAISE Architecture Team
- **Last Updated**: 2025-11-10
- **Review Cycle**: Monthly
- **Status**: Planning - Ready for Implementation
