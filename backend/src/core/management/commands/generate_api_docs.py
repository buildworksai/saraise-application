"""
Django management command to generate API documentation from DRF ViewSets.

Usage:
    python manage.py generate_api_docs --module workflow_automation
    python manage.py generate_api_docs --all-modules
"""
import inspect
import re
from pathlib import Path
from django.core.management.base import BaseCommand
from django.apps import apps
from rest_framework import viewsets
from rest_framework.routers import DefaultRouter


class Command(BaseCommand):
    help = 'Generate API documentation from DRF ViewSets'

    def add_arguments(self, parser):
        parser.add_argument(
            '--module',
            type=str,
            help='Module name in snake_case (e.g., workflow_automation)'
        )
        parser.add_argument(
            '--all-modules',
            action='store_true',
            help='Generate docs for all modules'
        )
        parser.add_argument(
            '--output-dir',
            type=str,
            default=None,
            help='Output directory (default: saraise-documentation/modules/01-foundation/{module}/)'
        )

    def handle(self, *args, **options):
        if options['all_modules']:
            self.generate_all_modules()
        elif options['module']:
            self.generate_module_docs(options['module'], options.get('output_dir'))
        else:
            self.stdout.write(self.style.ERROR('Must specify --module or --all-modules'))
            return

    def generate_all_modules(self):
        """Generate docs for all Foundation modules."""
        modules = [
            'workflow_automation', 'api_management', 'integration_platform',
            'customization_framework', 'ai_provider_configuration',
            'automation_orchestration', 'process_mining', 'document_intelligence',
            'dms', 'data_migration', 'metadata_modeling', 'blockchain_traceability',
            'billing_subscriptions', 'backup_disaster_recovery',
            'performance_monitoring', 'localization', 'regional'
        ]
        
        for module in modules:
            self.stdout.write(f'Generating docs for {module}...')
            self.generate_module_docs(module)

    def generate_module_docs(self, module_name, output_dir=None):
        """Generate API documentation for a module."""
        try:
            # Import module
            module_path = f'src.modules.{module_name}'
            module = __import__(f'{module_path}.api', fromlist=[''])
            
            # Find ViewSets
            viewset_classes = self._find_viewset_classes(module)
            
            if not viewset_classes:
                self.stdout.write(self.style.WARNING(f'No ViewSets found in {module_name}'))
                return
            
            # Generate documentation
            doc_content = self._generate_doc_content(module_name, viewset_classes)
            
            # Determine output path
            if output_dir:
                output_path = Path(output_dir) / f'{module_name.replace("_", "-")}' / 'API.md'
            else:
                # Default to documentation repo
                docs_base = Path(__file__).parent.parent.parent.parent.parent.parent.parent / 'saraise-documentation'
                output_path = docs_base / 'modules' / '01-foundation' / module_name.replace('_', '-') / 'API.md'
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(doc_content)
            
            self.stdout.write(self.style.SUCCESS(f'✅ Generated {output_path}'))
            
        except ImportError as e:
            self.stdout.write(self.style.ERROR(f'Failed to import {module_name}: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error generating docs for {module_name}: {e}'))

    def _find_viewset_classes(self, module):
        """Find all ViewSet classes in a module."""
        viewset_classes = []
        for name, obj in inspect.getmembers(module):
            if (inspect.isclass(obj) and 
                issubclass(obj, viewsets.ViewSet) and 
                obj is not viewsets.ViewSet):
                viewset_classes.append((name, obj))
        return viewset_classes

    def _generate_doc_content(self, module_name, viewset_classes):
        """Generate markdown documentation from ViewSets."""
        module_name_kebab = module_name.replace('_', '-')
        module_name_pascal = ''.join(word.capitalize() for word in module_name.split('_'))
        
        content = f'''<!-- SPDX-License-Identifier: Apache-2.0 -->
# {module_name_pascal} - API Documentation

**Version:** 1.0.0
**Last Updated:** {self._get_current_date()}
**Generated:** Automatically from DRF ViewSets

---

## Overview

This document describes the API endpoints for the {module_name_pascal} module.

## Endpoints

### Base Path

All endpoints are prefixed with `/api/v1/{module_name_kebab}/`

### Authentication

All endpoints require authentication. See [Authentication Documentation](../../../architecture/existing/authentication-and-session-management-spec.md) for details.

## Endpoint Reference

'''
        
        for viewset_name, viewset_class in viewset_classes:
            content += self._document_viewset(viewset_name, viewset_class, module_name_kebab)
        
        content += '''
## Request/Response Formats

See [API Standards](../../../standards/coding-standards.md) for standard request/response formats.

## Error Handling

See [Error Handling](../../../standards/coding-standards.md#error-handling) for standard error responses.

**Common Error Codes:**

- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Authentication required
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

## Rate Limiting

All endpoints are subject to rate limiting. See [Rate Limiting](../../../architecture/existing/rate-limiting.md) for details.

## Tenant Isolation

All endpoints automatically filter data by the authenticated user's tenant. Cross-tenant data access is not possible.
'''
        
        return content

    def _document_viewset(self, viewset_name, viewset_class, module_prefix):
        """Generate documentation for a ViewSet."""
        content = f'\n### {viewset_name}\n\n'
        
        # Get docstring
        docstring = inspect.getdoc(viewset_class)
        if docstring:
            content += f'{docstring}\n\n'
        
        # Document standard CRUD operations
        if hasattr(viewset_class, 'list'):
            content += self._document_endpoint('GET', f'/api/v1/{module_prefix}/resources/', 'List all resources')
        
        if hasattr(viewset_class, 'create'):
            content += self._document_endpoint('POST', f'/api/v1/{module_prefix}/resources/', 'Create a new resource')
        
        if hasattr(viewset_class, 'retrieve'):
            content += self._document_endpoint('GET', f'/api/v1/{module_prefix}/resources/{{id}}/', 'Get resource by ID')
        
        if hasattr(viewset_class, 'update'):
            content += self._document_endpoint('PUT', f'/api/v1/{module_prefix}/resources/{{id}}/', 'Update resource (full)')
        
        if hasattr(viewset_class, 'partial_update'):
            content += self._document_endpoint('PATCH', f'/api/v1/{module_prefix}/resources/{{id}}/', 'Update resource (partial)')
        
        if hasattr(viewset_class, 'destroy'):
            content += self._document_endpoint('DELETE', f'/api/v1/{module_prefix}/resources/{{id}}/', 'Delete resource')
        
        # Document custom actions
        for method_name in dir(viewset_class):
            if hasattr(getattr(viewset_class, method_name), 'mapping'):
                action = getattr(viewset_class, method_name)
                if hasattr(action, 'detail') and hasattr(action, 'methods'):
                    methods = list(action.methods)
                    detail = action.detail
                    url_path = getattr(action, 'url_path', method_name.replace('_', '-'))
                    
                    if detail:
                        url = f'/api/v1/{module_prefix}/resources/{{id}}/{url_path}/'
                    else:
                        url = f'/api/v1/{module_prefix}/resources/{url_path}/'
                    
                    for http_method in methods:
                        if http_method.upper() != 'OPTIONS':
                            content += self._document_endpoint(
                                http_method.upper(),
                                url,
                                f'Custom action: {method_name}'
                            )
        
        return content

    def _document_endpoint(self, method, url, description):
        """Document a single endpoint."""
        return f'''#### {method} {url}

{description}

**Request:** `{method}`

**Response:** `200 OK` (or appropriate status code)

```json
{{
  "id": "uuid",
  "tenant_id": "tenant-uuid",
  "name": "Resource Name",
  "description": "Resource description",
  "is_active": true,
  "config": {{}},
  "created_by": "user-uuid",
  "created_at": "2026-01-09T00:00:00Z",
  "updated_at": "2026-01-09T00:00:00Z"
}}
```

'''

    def _get_current_date(self):
        """Get current date in ISO format."""
        from datetime import date
        return date.today().isoformat()
