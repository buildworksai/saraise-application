# OpenSearch Architecture & Integration Guide

**Reference**: docs/architecture/architecture-freeze-and-change-control.md

## Overview

SARAISE uses **OpenSearch 2.11.1** (Apache 2.0 licensed Elasticsearch fork) for full-text search, analytics, and log aggregation across multi-tenant deployments.

**Key Properties**:
- **License**: Apache 2.0 (no licensing restrictions)
- **Version**: 2.11.1 (pinned in .agents/rules/03-tech-stack.md)
- **Role**: Full-text search, analytics, log aggregation, metrics
- **Cluster Mode**: Single-node (dev), Multi-node (staging/prod)
- **Tenant Isolation**: Logical indices per tenant (index naming: `tenant_{tenant_id}_{data_type}`)

## Architecture

### Index Structure

All OpenSearch indices follow tenant-scoped naming conventions:

```
tenant_{tenant_id}_{feature}_{version}
  tenant_abc123_customers_v1
  tenant_abc123_orders_v1
  tenant_abc123_audit_logs_v1
  tenant_def456_customers_v1  # Different tenant = different index
```

**CRITICAL**: Each index includes tenant_id field for runtime filtering:

```json
{
  "mappings": {
    "properties": {
      "tenant_id": {
        "type": "keyword"
      },
      "name": {
        "type": "text",
        "analyzer": "standard"
      },
      "created_at": {
        "type": "date"
      }
    }
  }
}
```

### Django Integration

**Installation**:
```bash
pip install opensearch-py==2.3.1  # Pinned version
pip install opensearch-dsl==2.1.0  # Query builder
```

**Configuration** (Django settings.py):
```python
OPENSEARCH_CONFIG = {
    'HOSTS': [os.environ.get('OPENSEARCH_URL', 'http://localhost:9200')],
    'HTTP_AUTH': (
        os.environ.get('OPENSEARCH_USER', 'admin'),
        os.environ.get('OPENSEARCH_PASSWORD', 'admin')
    ),
    'USE_SSL': os.environ.get('OPENSEARCH_USE_SSL', 'false').lower() == 'true',
    'VERIFY_CERTS': os.environ.get('OPENSEARCH_VERIFY_CERTS', 'false').lower() == 'true',
    'TIMEOUT': 30,
}
```

**Service Layer** (Django service):
```python
from opensearchpy import OpenSearch
from opensearch_dsl import Search, Q

class SearchService:
    """Service for OpenSearch operations with Row-Level Multitenancy."""
    
    def __init__(self, tenant_id: str):
        self.client = OpenSearch(**OPENSEARCH_CONFIG)
        self.tenant_id = tenant_id
    
    def index_customer(self, customer_id: str, data: dict) -> None:
        """Index customer document (tenant-scoped)."""
        index_name = f"tenant_{self.tenant_id}_customers_v1"
        
        document = {
            'tenant_id': self.tenant_id,
            'customer_id': customer_id,
            **data
        }
        
        self.client.index(
            index=index_name,
            id=customer_id,
            body=document
        )
    
    def search_customers(self, query: str) -> list:
        """Search customers (tenant-scoped)."""
        index_name = f"tenant_{self.tenant_id}_customers_v1"
        
        search_query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "match": {
                                "name": query
                            }
                        },
                        {
                            "term": {
                                "tenant_id": self.tenant_id
                            }
                        }
                    ]
                }
            }
        }
        
        results = self.client.search(index=index_name, body=search_query)
        return [hit['_source'] for hit in results['hits']['hits']]
```

### DRF Integration

**ViewSet Search Endpoint**:
```python
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

class CustomerViewSet(viewsets.ModelViewSet):
    """Customer API with OpenSearch full-text search."""
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        """Full-text search endpoint."""
        query = request.query_params.get('q', '').strip()
        
        if not query or len(query) < 2:
            return Response(
                {'error': 'Query must be at least 2 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = SearchService(tenant_id=request.user.tenant_id)
        results = service.search_customers(query)
        
        serializer = CustomerSerializer(results, many=True)
        return Response(serializer.data)
```

### Celery Task for Indexing

**Async indexing** (background task):
```python
from celery import shared_task

@shared_task
def index_customer_async(tenant_id: str, customer_id: str, data: dict):
    """Index customer in OpenSearch (async via Celery)."""
    service = SearchService(tenant_id=tenant_id)
    service.index_customer(customer_id, data)

# In model signal handler:
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Customer)
def customer_saved(sender, instance, created, **kwargs):
    """Auto-index customer on save."""
    index_customer_async.delay(
        instance.tenant_id,
        instance.id,
        instance.to_search_dict()
    )
```

## Deployment

### Development (Single-node)

```yaml
opensearch:
  image: opensearchproject/opensearch:2.11.1
  environment:
    - discovery.type=single-node
    - OPENSEARCH_INITIAL_ADMIN_PASSWORD=DevPassword123!
  ports:
    - "9200:9200"
  volumes:
    - opensearch_data:/usr/share/opensearch/data
```

### Production (Multi-node Cluster)

```yaml
opensearch-node1:
  image: opensearchproject/opensearch:2.11.1
  environment:
    - cluster.name=saraise-cluster
    - discovery.seed_hosts=opensearch-node1,opensearch-node2,opensearch-node3
    - cluster.initial_master_nodes=opensearch-node1,opensearch-node2,opensearch-node3
    - OPENSEARCH_INITIAL_ADMIN_PASSWORD=${OPENSEARCH_PASSWORD}
  ports:
    - "9200:9200"
  volumes:
    - opensearch_data_1:/usr/share/opensearch/data

# Repeat for opensearch-node2 and opensearch-node3
```

## Tenant Isolation

**CRITICAL**: OpenSearch does NOT enforce logical tenant isolation automatically.

**Enforcement Strategy**:
1. **Index Naming**: Tenant ID in index name (`tenant_{id}_feature`)
2. **Document Filtering**: Always filter by `tenant_id` field in queries
3. **Row-Level Security** (Optional, production): Use OpenSearch Security Plugin
4. **Audit Logging**: Log all searches to detect cross-tenant access attempts

**Example: Prevent Cross-Tenant Access**:
```python
def search_customers(self, query: str) -> list:
    """Search with mandatory tenant filtering."""
    
    # CRITICAL: Always include tenant_id in bool query
    search_query = {
        "query": {
            "bool": {
                "must": [
                    {"match": {"name": query}},
                    {"term": {"tenant_id": self.tenant_id}}  # ← MANDATORY
                ]
            }
        }
    }
    
    return self.client.search(index=..., body=search_query)
```

## Performance Tuning

### Index Settings (Production)

```python
index_settings = {
    "settings": {
        "number_of_shards": 3,
        "number_of_replicas": 2,
        "refresh_interval": "30s",  # Balance between latency and throughput
        "index.codec": "best_compression",
        "index.store.type": "niofs"
    },
    "mappings": {
        "properties": {
            "tenant_id": {"type": "keyword"},
            "name": {
                "type": "text",
                "analyzer": "standard",
                "fields": {"keyword": {"type": "keyword"}}
            },
            "created_at": {"type": "date"}
        }
    }
}

self.client.indices.create(index=index_name, body=index_settings)
```

### Bulk Indexing (Celery Batch Task)

```python
@shared_task
def bulk_index_customers(tenant_id: str, customer_data_list: list):
    """Bulk index multiple customers (higher throughput)."""
    service = SearchService(tenant_id=tenant_id)
    
    bulk_body = []
    for customer_data in customer_data_list:
        bulk_body.append({
            "index": {
                "_index": f"tenant_{tenant_id}_customers_v1",
                "_id": customer_data['id']
            }
        })
        bulk_body.append({
            'tenant_id': tenant_id,
            **customer_data
        })
    
    service.client.bulk(body=bulk_body)
```

## Monitoring & Maintenance

### Health Checks

```python
def opensearch_health_check() -> bool:
    """Verify OpenSearch cluster health."""
    client = OpenSearch(**OPENSEARCH_CONFIG)
    health = client.cluster.health()
    return health['status'] in ['green', 'yellow']
```

### Index Cleanup (Celery Periodic Task)

```python
from celery.schedules import crontab
from celery import shared_task

@shared_task
def cleanup_old_indices():
    """Delete indices older than 90 days."""
    client = OpenSearch(**OPENSEARCH_CONFIG)
    
    indices = client.indices.get(index="tenant_*")
    cutoff_date = datetime.now() - timedelta(days=90)
    
    for index_name in indices:
        # Parse date from index metadata and delete if old
        pass
```

### Backup & Recovery

```python
@shared_task
def backup_opensearch(backup_location: str):
    """Backup OpenSearch indices to S3."""
    client = OpenSearch(**OPENSEARCH_CONFIG)
    
    # Register snapshot repository
    client.snapshot.create_repository(
        repository='saraise_backups',
        body={
            'type': 's3',
            'settings': {
                'bucket': backup_location,
                'region': 'us-east-1'
            }
        }
    )
    
    # Create snapshot
    client.snapshot.create(
        repository='saraise_backups',
        snapshot=f'backup_{datetime.now().isoformat()}'
    )
```

## Security

### Authentication & Authorization

**Production**:
- Use OpenSearch Security Plugin (included in OpenSearch 2.x)
- Enable HTTPS/TLS for all connections
- Use strong admin credentials (Vault-managed)
- Enforce role-based access control

**Configuration** (production Django settings):
```python
OPENSEARCH_CONFIG = {
    'HOSTS': [os.environ.get('OPENSEARCH_URL')],
    'HTTP_AUTH': (
        os.environ.get('OPENSEARCH_USER'),
        os.environ.get('OPENSEARCH_PASSWORD')
    ),
    'USE_SSL': True,
    'VERIFY_CERTS': True,
    'CA_CERTS': '/etc/ssl/certs/opensearch-ca.crt',
}
```

### Encryption

- **In Transit**: TLS 1.2+
- **At Rest**: Enable OpenSearch encryption (commercial plugin or disk encryption)
- **Backups**: Encrypt S3 backups with AWS KMS

## Reference

- **OpenSearch Docs**: https://opensearch.org/docs/latest/
- **Django Integration**: See `backend/src/services/search-service.py`
- **API Examples**: See `backend/src/modules/*/views.py` (search endpoints)
- **Testing**: See `backend/tests/test_search_*.py`
- **Architecture Decision**: docs/architecture/adr/ (search technology selection)

