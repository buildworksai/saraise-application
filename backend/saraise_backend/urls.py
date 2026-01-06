"""
URL configuration for SARAISE backend.
"""
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from src.core.metrics import metrics

urlpatterns = [
    # Health check endpoint
    path('health/', lambda request: None),
    path('metrics/', metrics),
    
    # OpenAPI Schema
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # ===== Authentication Routes =====
    path('api/v1/auth/', include('src.core.auth_urls')),
    
    # ===== Module Routes =====
    # AI Agent Management
    path('api/v1/ai-agents/', include('src.modules.ai_agent_management.urls')),
    
    # Platform Management
    path('api/v1/platform/', include('src.modules.platform_management.urls')),
    
    # Tenant Management
    path('api/v1/tenant-management/', include('src.modules.tenant_management.urls')),
    
    # Security & Access Control
    path('api/v1/security-access-control/', include('src.modules.security_access_control.urls')),
    
    # Add other module routes here as they're implemented
]
