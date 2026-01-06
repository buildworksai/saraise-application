#!/usr/bin/env python3
"""
Module Generation Script for SARAISE

Generates a new module from the AI Agent Management template.
Automates 70% of module implementation boilerplate.

Usage:
    python scripts/module-generation/generate_module.py \
        --name platform-management \
        --category foundation \
        --description "Platform administration and configuration"
"""
import os
import sys
import argparse
import re
from pathlib import Path
from typing import Dict, List
import shutil


class ModuleGenerator:
    """Generates SARAISE modules from template."""

    TEMPLATE_MODULE = "ai_agent_management"
    BACKEND_BASE = Path(__file__).parent.parent.parent / "backend" / "src" / "modules"
    FRONTEND_BASE = Path(__file__).parent.parent.parent / "frontend" / "src" / "modules"
    DOCS_BASE = Path(__file__).parent.parent.parent / "docs" / "modules"

    CATEGORIES = {
        'foundation': '01-foundation',
        'core': '02-core',
        'industry': '03-industry-specific'
    }

    def __init__(self, module_name: str, category: str, description: str):
        """
        Initialize module generator.

        Args:
            module_name: Kebab-case module name (e.g., 'platform-management')
            category: Module category ('foundation', 'core', 'industry')
            description: Brief module description
        """
        self.module_name = module_name
        self.module_name_snake = module_name.replace('-', '_')
        self.module_name_pascal = self._to_pascal_case(module_name)
        self.category = category
        self.description = description

        self.template_backend = self.BACKEND_BASE / self.TEMPLATE_MODULE
        self.target_backend = self.BACKEND_BASE / self.module_name_snake
        self.target_frontend = self.FRONTEND_BASE / self.module_name_snake
        self.target_docs = self.DOCS_BASE / self.CATEGORIES[category] / self.module_name

    @staticmethod
    def _to_pascal_case(kebab_str: str) -> str:
        """Convert kebab-case to PascalCase."""
        return ''.join(word.capitalize() for word in kebab_str.split('-'))

    def generate(self):
        """Generate module from template."""
        print(f"🚀 Generating module: {self.module_name}")
        print(f"   Category: {self.category}")
        print(f"   Description: {self.description}")
        print()

        # Step 1: Generate backend
        self._generate_backend()

        # Step 2: Generate frontend
        self._generate_frontend()

        # Step 3: Generate documentation
        self._generate_documentation()

        # Step 4: Print next steps
        self._print_next_steps()

    def _generate_backend(self):
        """Generate backend module structure."""
        print("📦 Generating backend module...")

        # Create directory
        self.target_backend.mkdir(parents=True, exist_ok=True)

        # Copy template files
        files_to_copy = [
            '__init__.py',
            'models.py',
            'services.py',
            'permissions.py',
            'policies.py',
        ]

        for file in files_to_copy:
            src = self.template_backend / file
            dst = self.target_backend / file
            if src.exists():
                shutil.copy2(src, dst)
                self._replace_placeholders(dst)
                print(f"   ✅ Created {file}")

        # Create new files (not in template)
        self._create_api_file()
        self._create_serializers_file()
        self._create_urls_file()
        self._create_health_file()
        self._create_manifest_file()

        # Create subdirectories
        (self.target_backend / 'migrations').mkdir(exist_ok=True)
        (self.target_backend / 'migrations' / '__init__.py').touch()
        (self.target_backend / 'tests').mkdir(exist_ok=True)
        (self.target_backend / 'tests' / '__init__.py').touch()

        print("   ✅ Backend structure created")

    def _create_api_file(self):
        """Create api.py from template."""
        content = f'''"""
DRF ViewSets for {self.module_name_pascal} module.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import {self.module_name_pascal}  # TODO: Update model name
from .serializers import {self.module_name_pascal}Serializer


class {self.module_name_pascal}ViewSet(viewsets.ModelViewSet):
    """
    ViewSet for {self.module_name_pascal} CRUD operations.

    Endpoints:
    - GET /api/v1/{self.module_name}/resources/ - List all resources
    - POST /api/v1/{self.module_name}/resources/ - Create resource
    - GET /api/v1/{self.module_name}/resources/{{id}}/ - Get resource detail
    - PUT /api/v1/{self.module_name}/resources/{{id}}/ - Update resource
    - DELETE /api/v1/{self.module_name}/resources/{{id}}/ - Delete resource
    """

    serializer_class = {self.module_name_pascal}Serializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter resources by tenant_id from authenticated user."""
        # TODO: Update model reference
        return {self.module_name_pascal}.objects.filter(
            tenant_id=self.request.user.tenant_id
        )

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        serializer.save(tenant_id=self.request.user.tenant_id)
'''

        (self.target_backend / 'api.py').write_text(content)
        print("   ✅ Created api.py")

    def _create_serializers_file(self):
        """Create serializers.py from template."""
        content = f'''"""
DRF Serializers for {self.module_name_pascal} module.
"""
from rest_framework import serializers

from .models import {self.module_name_pascal}  # TODO: Update model name


class {self.module_name_pascal}Serializer(serializers.ModelSerializer):
    """Serializer for {self.module_name_pascal} model."""

    class Meta:
        model = {self.module_name_pascal}
        fields = ['id', 'tenant_id', 'name', 'description', 'created_at', 'updated_at']
        read_only_fields = ['id', 'tenant_id', 'created_at', 'updated_at']

    def validate(self, data):
        """Custom validation."""
        # TODO: Add validation logic
        return data
'''

        (self.target_backend / 'serializers.py').write_text(content)
        print("   ✅ Created serializers.py")

    def _create_urls_file(self):
        """Create urls.py from template."""
        content = f'''"""
URL routing for {self.module_name_pascal} module.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api import {self.module_name_pascal}ViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r'resources', {self.module_name_pascal}ViewSet, basename='resource')

# URL patterns
urlpatterns = [
    path('', include(router.urls)),
    path('health/', health_check, name='health_check'),
]
'''

        (self.target_backend / 'urls.py').write_text(content)
        print("   ✅ Created urls.py")

    def _create_health_file(self):
        """Create health.py from template."""
        content = f'''"""
Health check endpoint for {self.module_name_pascal} module.
"""
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db import connection


@api_view(['GET'])
def health_check(request):
    """
    Health check endpoint.

    Returns:
    - 200 OK if healthy
    - 503 Service Unavailable if unhealthy
    """
    health_status = {{
        'status': 'healthy',
        'module': '{self.module_name}',
        'checks': {{}}
    }}

    # Check database connectivity
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_status['checks']['database'] = 'ok'
    except Exception as e:
        health_status['status'] = 'unhealthy'
        health_status['checks']['database'] = f'error: {{str(e)}}'

    status_code = 200 if health_status['status'] == 'healthy' else 503
    return Response(health_status, status=status_code)
'''

        (self.target_backend / 'health.py').write_text(content)
        print("   ✅ Created health.py")

    def _create_manifest_file(self):
        """Create manifest.yaml from template."""
        content = f'''name: {self.module_name}
version: 1.0.0
description: {self.description}
type: {self.category}
lifecycle: managed

dependencies:
  - core-identity >=1.0
  - core-audit >=1.0

permissions:
  - {self.module_name_snake}.resource:create
  - {self.module_name_snake}.resource:read
  - {self.module_name_snake}.resource:update
  - {self.module_name_snake}.resource:delete

sod_actions:
  - {self.module_name_snake}.resource:create
  - {self.module_name_snake}.resource:approve

search_indexes:
  - {self.module_name_snake}_resources

ai_tools:
  - {self.module_name_snake}_action
'''

        (self.target_backend / 'manifest.yaml').write_text(content)
        print("   ✅ Created manifest.yaml")

    def _generate_frontend(self):
        """Generate frontend module structure."""
        print("\n🎨 Generating frontend module...")

        # Create directory structure
        self.target_frontend.mkdir(parents=True, exist_ok=True)
        (self.target_frontend / 'pages').mkdir(exist_ok=True)
        (self.target_frontend / 'components').mkdir(exist_ok=True)
        (self.target_frontend / 'services').mkdir(exist_ok=True)
        (self.target_frontend / 'types').mkdir(exist_ok=True)
        (self.target_frontend / 'tests').mkdir(exist_ok=True)

        # Create service client
        self._create_service_client()

        # Create list page
        self._create_list_page()

        # Create detail page
        self._create_detail_page()

        print("   ✅ Frontend structure created")

    def _create_service_client(self):
        """Create frontend service client."""
        content = f'''/**
 * Service client for {self.module_name_pascal} module.
 */
import {{ apiClient }} from '@/services/api-client';
import type {{ Resource, ResourceCreate, ResourceUpdate }} from '@/types/api';

export const {self.module_name_snake}Service = {{
  listResources: () =>
    apiClient.get<Resource[]>('/api/v1/{self.module_name}/resources/'),

  getResource: (id: string) =>
    apiClient.get<Resource>(`/api/v1/{self.module_name}/resources/${{id}}/`),

  createResource: (data: ResourceCreate) =>
    apiClient.post<Resource>('/api/v1/{self.module_name}/resources/', data),

  updateResource: (id: string, data: ResourceUpdate) =>
    apiClient.put<Resource>(`/api/v1/{self.module_name}/resources/${{id}}/`, data),

  deleteResource: (id: string) =>
    apiClient.delete(`/api/v1/{self.module_name}/resources/${{id}}/`),
}};
'''

        (self.target_frontend / 'services' / f'{self.module_name_snake}-service.ts').write_text(content)
        print("   ✅ Created service client")

    def _create_list_page(self):
        """Create list page."""
        content = f'''/**
 * List page for {self.module_name_pascal} module.
 */
import {{ useQuery }} from '@tanstack/react-query';
import {{ {self.module_name_snake}Service }} from '../services/{self.module_name_snake}-service';

export const ListPage = () => {{
  const {{ data, isLoading }} = useQuery({{
    queryKey: ['{self.module_name_snake}-resources'],
    queryFn: {self.module_name_snake}Service.listResources,
  }});

  if (isLoading) return <div>Loading...</div>;

  return (
    <div>
      <h1>{self.module_name_pascal} Resources</h1>
      {{/* TODO: Add DataTable component */}}
      <pre>{{JSON.stringify(data, null, 2)}}</pre>
    </div>
  );
}};
'''

        (self.target_frontend / 'pages' / 'ListPage.tsx').write_text(content)
        print("   ✅ Created ListPage.tsx")

    def _create_detail_page(self):
        """Create detail page."""
        content = f'''/**
 * Detail page for {self.module_name_pascal} module.
 */
import {{ useQuery }} from '@tanstack/react-query';
import {{ useParams }} from 'react-router-dom';
import {{ {self.module_name_snake}Service }} from '../services/{self.module_name_snake}-service';

export const DetailPage = () => {{
  const {{ id }} = useParams<{{ id: string }}>();

  const {{ data, isLoading }} = useQuery({{
    queryKey: ['{self.module_name_snake}-resource', id],
    queryFn: () => {self.module_name_snake}Service.getResource(id!),
    enabled: !!id,
  }});

  if (isLoading) return <div>Loading...</div>;
  if (!data) return <div>Resource not found</div>;

  return (
    <div>
      <h1>{self.module_name_pascal} Detail</h1>
      {{/* TODO: Add detail view */}}
      <pre>{{JSON.stringify(data, null, 2)}}</pre>
    </div>
  );
}};
'''

        (self.target_frontend / 'pages' / 'DetailPage.tsx').write_text(content)
        print("   ✅ Created DetailPage.tsx")

    def _generate_documentation(self):
        """Generate documentation structure."""
        print("\n📚 Generating documentation...")

        # Create docs directory
        self.target_docs.mkdir(parents=True, exist_ok=True)

        # Create README
        self._create_readme()

        # Create API docs placeholder
        (self.target_docs / 'API.md').write_text(f'# {self.module_name_pascal} API Documentation\n\nTODO: Document API endpoints\n')

        # Create user guide placeholder
        (self.target_docs / 'USER-GUIDE.md').write_text(f'# {self.module_name_pascal} User Guide\n\nTODO: Write user guide\n')

        print("   ✅ Documentation structure created")

    def _create_readme(self):
        """Create module README."""
        content = f'''# {self.module_name_pascal}

**Category:** {self.category.capitalize()}
**Status:** In Development
**Version:** 1.0.0

## Description

{self.description}

## Features

- TODO: List key features

## Installation

This module is part of the SARAISE platform and is installed automatically for tenants based on their subscription plan.

## Usage

TODO: Add usage instructions

## API Endpoints

See [API.md](./API.md) for complete API documentation.

## Development

### Backend

Location: `backend/src/modules/{self.module_name_snake}/`

### Frontend

Location: `frontend/src/modules/{self.module_name_snake}/`

### Running Tests

```bash
# Backend tests
cd backend
pytest src/modules/{self.module_name_snake}/tests/ -v

# Frontend tests
cd frontend
npm test -- {self.module_name_snake}
```

## License

Apache-2.0
'''

        (self.target_docs / 'README.md').write_text(content)
        print("   ✅ Created README.md")

    def _replace_placeholders(self, file_path: Path):
        """Replace template placeholders in file."""
        content = file_path.read_text()

        # Replace module references
        content = content.replace('ai_agent_management', self.module_name_snake)
        content = content.replace('AiAgentManagement', self.module_name_pascal)
        content = content.replace('AI Agent Management', self.module_name_pascal)

        file_path.write_text(content)

    def _print_next_steps(self):
        """Print next steps for developer."""
        print("\n✅ Module generation complete!")
        print("\n📋 Next Steps:")
        print(f"\n1. Update models in: backend/src/modules/{self.module_name_snake}/models.py")
        print(f"   - Define your domain models")
        print(f"   - Ensure all tenant-scoped models have tenant_id field")
        print(f"\n2. Create Django migrations:")
        print(f"   cd backend")
        print(f"   python manage.py makemigrations {self.module_name_snake}")
        print(f"   python manage.py migrate")
        print(f"\n3. Update serializers in: backend/src/modules/{self.module_name_snake}/serializers.py")
        print(f"   - Add validation logic")
        print(f"   - Add nested serializers if needed")
        print(f"\n4. Update ViewSets in: backend/src/modules/{self.module_name_snake}/api.py")
        print(f"   - Add custom actions")
        print(f"   - Add permission checks")
        print(f"\n5. Register routes in: backend/saraise_backend/urls.py")
        print(f"   urlpatterns += [")
        print(f"       path('api/v1/{self.module_name}/', include('src.modules.{self.module_name_snake}.urls')),")
        print(f"   ]")
        print(f"\n6. Implement frontend pages in: frontend/src/modules/{self.module_name_snake}/pages/")
        print(f"   - Complete ListPage.tsx")
        print(f"   - Complete DetailPage.tsx")
        print(f"   - Create CreatePage.tsx")
        print(f"   - Create EditPage.tsx")
        print(f"\n7. Add module routes to: frontend/src/App.tsx")
        print(f"\n8. Write tests:")
        print(f"   - Backend: backend/src/modules/{self.module_name_snake}/tests/")
        print(f"   - Frontend: frontend/src/modules/{self.module_name_snake}/tests/")
        print(f"\n9. Update documentation:")
        print(f"   - docs/modules/{self.CATEGORIES[self.category]}/{self.module_name}/API.md")
        print(f"   - docs/modules/{self.CATEGORIES[self.category]}/{self.module_name}/USER-GUIDE.md")
        print(f"\n10. Test end-to-end:")
        print(f"    - Start backend: cd backend && python manage.py runserver")
        print(f"    - Start frontend: cd frontend && npm run dev")
        print(f"    - Test API: curl http://localhost:8000/api/v1/{self.module_name}/health/")
        print(f"    - Test UI: http://localhost:5173/{self.module_name}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate SARAISE module from template'
    )
    parser.add_argument(
        '--name',
        required=True,
        help='Module name in kebab-case (e.g., platform-management)'
    )
    parser.add_argument(
        '--category',
        required=True,
        choices=['foundation', 'core', 'industry'],
        help='Module category'
    )
    parser.add_argument(
        '--description',
        required=True,
        help='Brief module description'
    )

    args = parser.parse_args()

    generator = ModuleGenerator(
        module_name=args.name,
        category=args.category,
        description=args.description
    )

    generator.generate()


if __name__ == '__main__':
    main()

