---
description: Performance optimization standards and best practices for SARAISE infrastructure
globs: backend/src/**/*.py, frontend/src/**/*.{ts,tsx}
alwaysApply: true
---

# ⚡ SARAISE Performance Optimization Standards

**⚠️ CRITICAL**: All services MUST meet performance targets and follow optimization patterns for production scalability.

## SARAISE-18001 Performance Targets

### Response Time Targets
- **API Endpoints**: < 200ms (95th percentile)
- **Database Queries**: < 100ms (95th percentile)
- **Redis Operations**: < 10ms (95th percentile)
- **File Uploads**: < 2s (95th percentile)
- **Page Load**: < 3s (95th percentile)

### Throughput Targets
- **API Requests**: > 1000 requests/second
- **Database Connections**: Support 100+ concurrent connections
- **Redis Operations**: > 10,000 operations/second
- **File Processing**: > 100 files/minute

### Resource Usage Limits
- **Memory**: < 80% of available memory
- **CPU**: < 70% of available CPU
- **Disk I/O**: < 80% of available disk bandwidth
- **Network**: < 80% of available bandwidth

## SARAISE-18002 Database Performance Optimization

### Connection Pooling
```python
# ✅ REQUIRED: Django database connection pooling
# backend/settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'saraise',
        'USER': 'postgres',
        'PASSWORD': os.getenv('POSTGRES_PASSWORD'),
        'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
        'CONN_MAX_AGE': 3600,           # Connection pooling: 1 hour
        'OPTIONS': {
            'connect_timeout': 30,      # Connection timeout
            'keepalives': 1,            # Enable TCP keepalive
            'keepalives_idle': 30,      # Idle time before keepalive
        }
    }
}
```

### Query Optimization
```python
# ✅ REQUIRED: Optimized Django ORM queries
from django.db.models import Prefetch, Q
from django.views.decorators.cache import cache_page

# Good - Use select_related for foreign keys
def get_users_with_roles(tenant_id):
    """Optimized query with eager loading"""
    return User.objects.filter(
        tenant_id=tenant_id
    ).select_related('profile').prefetch_related('roles')[:100]

# Good - Use database-level pagination with DRF Pagination
from rest_framework.pagination import PageNumberPagination

class StandardPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100

# Good - Use database-level filtering
def get_users_paginated(request, tenant_id):
    """Paginated query with proper filtering"""
    users = User.objects.filter(
        tenant_id=tenant_id,
        is_active=True
    ).order_by('-created_at')
    # Pagination handled by DRF pagination class
    return users
```

## SARAISE-18003 Redis Performance Optimization

### Connection Pooling
```python
# ✅ REQUIRED: Redis connection pooling
import redis
from redis import ConnectionPool
from src.core.urls import get_redis_url

class OptimizedRedisService:
    def __init__(self):
        redis_url = get_redis_url()
        self.pool = ConnectionPool.from_url(
            redis_url,
            max_connections=50,           # Maximum connections in pool
            retry_on_timeout=True,       # Retry on timeout
            socket_keepalive=True,       # Keep connections alive
            socket_connect_timeout=5,    # Connection timeout
            socket_timeout=5,            # Socket timeout
            decode_responses=True
        )
        self.client = redis.Redis(connection_pool=self.pool)

    async def get_with_pipeline(self, keys: list):
        """Use pipeline for multiple operations"""
        pipe = self.client.pipeline()
        for key in keys:
            pipe.get(key)
        return pipe.execute()
```

## SARAISE-18004 API Performance Optimization

### Response Compression
```python
# ✅ REQUIRED: Response compression middleware (Django)
from django.middleware.gzip import GZipMiddleware

# Add to MIDDLEWARE in settings.py:
# 'django.middleware.gzip.GZipMiddleware',

# Gzip settings
GZIP_MIN_LENGTH = 1000  # Compress responses > 1KB
```

### Async Processing
```python
# ✅ REQUIRED: Async processing for I/O operations
import asyncio
from concurrent.futures import ThreadPoolExecutor

class AsyncProcessor:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=10)

    async def process_files_async(self, files: list):
        """Process multiple files concurrently"""
        tasks = []
        for file in files:
            task = asyncio.create_task(self.process_single_file(file))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
```

## SARAISE-18005 Frontend Performance Optimization

### Code Splitting
```typescript
// ✅ REQUIRED: Code splitting for better performance
// frontend/src/App.tsx
import { lazy, Suspense } from 'react';
import { Routes, Route } from 'react-router-dom';

// Lazy load components
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Users = lazy(() => import('./pages/Users'));
const Settings = lazy(() => import('./pages/Settings'));

function App() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/users" element={<Users />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </Suspense>
  );
}
```

### Image Optimization
```typescript
// ✅ REQUIRED: Image optimization component
// frontend/src/components/OptimizedImage.tsx
import { useState } from 'react';

interface OptimizedImageProps {
  src: string;
  alt: string;
  width?: number;
  height?: number;
  className?: string;
}

export function OptimizedImage({ src, alt, width, height, className }: OptimizedImageProps) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  if (error) {
    return <div className="image-placeholder">Image failed to load</div>;
  }

  return (
    <div className={`image-container ${className}`}>
      {!loaded && <div className="image-skeleton" />}
      <img
        src={src}
        alt={alt}
        width={width}
        height={height}
        onLoad={() => setLoaded(true)}
        onError={() => setError(true)}
        style={{ display: loaded ? 'block' : 'none' }}
        loading="lazy"
      />
    </div>
  );
}
```

## SARAISE-18006 File Processing Optimization

### Streaming File Processing
```python
# ✅ REQUIRED: Streaming file processing for large files (Django)
from django.core.files.uploadhandler import UploadFileException
from rest_framework.parsers import FileUploadParser

class StreamingFileUploadView(APIView):
    """Process large file uploads in chunks"""
    parser_classes = (FileUploadParser,)

    def put(self, request, filename, *args, **kwargs):
        file_obj = request.FILES['file']
        # Django automatically handles chunked processing
        return Response({'filename': filename}, status=201)
```

## SARAISE-18007 Memory Optimization

### Memory-Efficient Data Processing
```python
# ✅ REQUIRED: Memory-efficient data processing
import gc
from typing import Iterator

class MemoryEfficientProcessor:
    def __init__(self, batch_size: int = 1000):
        self.batch_size = batch_size

    def process_large_dataset(self, data_source: Iterator) -> Iterator:
        """Process large dataset in batches to manage memory"""
        batch = []

        for item in data_source:
            batch.append(item)

            if len(batch) >= self.batch_size:
                # Process batch
                yield from self.process_batch(batch)

                # Clear batch and force garbage collection
                batch.clear()
                gc.collect()

        # Process remaining items
        if batch:
            yield from self.process_batch(batch)
```

## SARAISE-18008 Network Optimization

### HTTP Connection Reuse
```python
# ✅ REQUIRED: HTTP connection reuse
import httpx

class OptimizedHTTPClient:
    def __init__(self):
        self.client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=30
            ),
            timeout=httpx.Timeout(30.0)
        )

    async def make_request(self, url: str, method: str = "GET", **kwargs):
        """Make HTTP request with connection reuse"""
        try:
            response = await self.client.request(method, url, **kwargs)
            return response
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Request timeout")
```

## SARAISE-18009 Performance Monitoring

### Performance Metrics Collection
```python
# ✅ REQUIRED: Performance metrics collection
import time
from functools import wraps

def track_performance(metric_name: str):
    """Decorator to track function performance"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time

                # Record success metric
                PERFORMANCE_METRICS.labels(
                    function=func.__name__,
                    metric=metric_name,
                    status="success"
                ).observe(duration)

                return result
            except Exception as e:
                duration = time.time() - start_time

                # Record error metric
                PERFORMANCE_METRICS.labels(
                    function=func.__name__,
                    metric=metric_name,
                    status="error"
                ).observe(duration)

                raise e
        return wrapper
    return decorator
```

## SARAISE-18010 Performance Testing

### Load Testing Guidelines
```python
# ✅ REQUIRED: Load testing implementation
import asyncio
import aiohttp
import time
from typing import List, Dict, Any

class LoadTester:
    def __init__(self, base_url: str, concurrent_users: int = 100):
        self.base_url = base_url
        self.concurrent_users = concurrent_users
        self.results: List[Dict[str, Any]] = []

    async def run_load_test(self, endpoint: str, duration: int = 60):
        """Run load test for specified duration"""
        start_time = time.time()
        tasks = []

        # Create concurrent user tasks
        for i in range(self.concurrent_users):
            task = asyncio.create_task(
                self.simulate_user(endpoint, start_time + duration)
            )
            tasks.append(task)

        # Wait for all tasks to complete
        await asyncio.gather(*tasks)

        # Calculate results
        return self.calculate_results()

    def calculate_results(self) -> Dict[str, Any]:
        """Calculate load test results"""
        if not self.results:
            return {}

        durations = [r['duration'] for r in self.results]
        status_codes = [r['status_code'] for r in self.results]

        return {
            'total_requests': len(self.results),
            'success_rate': sum(1 for s in status_codes if 200 <= s < 300) / len(status_codes),
            'avg_response_time': sum(durations) / len(durations),
            'p95_response_time': sorted(durations)[int(len(durations) * 0.95))],
            'p99_response_time': sorted(durations)[int(len(durations) * 0.99)],
        }
```

---

**Next Steps**: Implement these performance optimization patterns across all services. Use load testing to validate performance targets and monitor metrics continuously.
