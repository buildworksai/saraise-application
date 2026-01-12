#!/usr/bin/env python3
"""
Generate API documentation from DRF ViewSet files.

Parses ViewSet Python files to extract endpoint information and generate API.md.
"""
import ast
import re
from pathlib import Path
from typing import List, Dict, Optional

BACKEND_BASE = Path(__file__).parent.parent / "backend" / "src" / "modules"
DOCS_BASE = Path(__file__).parent.parent.parent / "saraise-documentation" / "modules" / "01-foundation"

# Module name mappings
MODULE_BATCHES = {
    1: ["workflow_automation", "api_management", "integration_platform", "customization_framework"],
    2: ["ai_provider_configuration", "automation_orchestration", "process_mining", "document_intelligence"],
    3: ["dms", "data_migration", "metadata_modeling", "blockchain_traceability"],
    4: ["billing_subscriptions", "backup_disaster_recovery", "performance_monitoring", "localization"],
    5: ["regional"],
}


class ViewSetParser(ast.NodeVisitor):
    """Parse ViewSet class to extract endpoint information."""
    
    def __init__(self):
        self.viewset_name = None
        self.docstring = None
        self.has_list = False
        self.has_create = False
        self.has_retrieve = False
        self.has_update = False
        self.has_partial_update = False
        self.has_destroy = False
        self.custom_actions = []
        self.serializer_class = None
        self.base_name = None
    
    def visit_ClassDef(self, node):
        """Visit class definition."""
        # Check if class inherits from ViewSet (directly or indirectly)
        is_viewset = False
        for base in node.bases:
            if isinstance(base, ast.Name):
                if 'ViewSet' in base.id:
                    is_viewset = True
                    break
            elif isinstance(base, ast.Attribute):
                # Handle viewsets.ModelViewSet, viewsets.ViewSet, etc.
                if base.attr and 'ViewSet' in base.attr:
                    is_viewset = True
                    break
        
        if is_viewset:
            self.viewset_name = node.name
            self.docstring = ast.get_docstring(node)
            
            # Check for standard methods
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    if item.name == 'list':
                        self.has_list = True
                    elif item.name == 'create':
                        self.has_create = True
                    elif item.name == 'retrieve':
                        self.has_retrieve = True
                    elif item.name == 'update':
                        self.has_update = True
                    elif item.name == 'partial_update':
                        self.has_partial_update = True
                    elif item.name == 'destroy':
                        self.has_destroy = True
                    elif hasattr(item, 'decorator_list'):
                        # Check for @action decorator
                        for decorator in item.decorator_list:
                            if isinstance(decorator, ast.Call):
                                if isinstance(decorator.func, ast.Name) and decorator.func.id == 'action':
                                    # Extract action details
                                    detail = True
                                    methods = ['post']
                                    url_path = item.name.replace('_', '-')
                                    
                                    for keyword in decorator.keywords:
                                        if keyword.arg == 'detail':
                                            detail = keyword.value.value if isinstance(keyword.value, ast.Constant) else True
                                        elif keyword.arg == 'methods':
                                            methods = [m.value if isinstance(m, ast.Constant) else str(m) for m in keyword.value.elts] if isinstance(keyword.value, ast.List) else ['post']
                                        elif keyword.arg == 'url_path':
                                            url_path = keyword.value.value if isinstance(keyword.value, ast.Constant) else item.name.replace('_', '-')
                                    
                                    self.custom_actions.append({
                                        'name': item.name,
                                        'url_path': url_path,
                                        'detail': detail,
                                        'methods': methods,
                                        'docstring': ast.get_docstring(item)
                                    })
            
            # Extract serializer_class
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == 'serializer_class':
                            if isinstance(item.value, ast.Name):
                                self.serializer_class = item.value.id
                            elif isinstance(item.value, ast.Attribute):
                                self.serializer_class = item.value.attr
            
            # Extract basename from router registration (if present in urls.py)
            # This would require parsing urls.py separately
        
        self.generic_visit(node)


def parse_viewset(api_file: Path) -> Optional[ViewSetParser]:
    """Parse a ViewSet file and extract information."""
    try:
        content = api_file.read_text()
        tree = ast.parse(content)
        
        parser = ViewSetParser()
        parser.visit(tree)
        
        if parser.viewset_name:
            return parser
    except Exception as e:
        print(f"   ⚠️  Error parsing {api_file}: {e}")
    
    return None


def get_basename_from_urls(urls_file: Path) -> str:
    """Extract basename from urls.py router registration."""
    try:
        content = urls_file.read_text()
        # Look for router.register pattern
        match = re.search(r'router\.register\(r\'([^\']+)\'', content)
        if match:
            return match.group(1)
    except:
        pass
    return 'resource'  # Default


def generate_api_doc(module_name: str, viewset_parser: ViewSetParser, basename: str) -> str:
    """Generate API.md content from ViewSet parser."""
    module_name_kebab = module_name.replace('_', '-')
    module_name_pascal = ''.join(word.capitalize() for word in module_name.split('_'))
    
    from datetime import date
    current_date = date.today().isoformat()
    
    content = f'''<!-- SPDX-License-Identifier: Apache-2.0 -->
# {module_name_pascal} - API Documentation

**Version:** 1.0.0
**Last Updated:** {current_date}
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

### {viewset_parser.viewset_name}

'''
    
    if viewset_parser.docstring:
        content += f'{viewset_parser.docstring}\n\n'
    
    # Document standard CRUD operations
    if viewset_parser.has_list:
        content += f'''#### GET /api/v1/{module_name_kebab}/{basename}/

List all resources for the authenticated user's tenant.

**Response:** `200 OK`

```json
[
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
]
```

'''
    
    if viewset_parser.has_create:
        content += f'''#### POST /api/v1/{module_name_kebab}/{basename}/

Create a new resource.

**Request Body:**

```json
{{
  "name": "Resource Name",
  "description": "Resource description",
  "config": {{}}
}}
```

**Response:** `201 Created`

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
    
    if viewset_parser.has_retrieve:
        content += f'''#### GET /api/v1/{module_name_kebab}/{basename}/{{id}}/

Get resource detail by ID.

**Response:** `200 OK`

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
    
    if viewset_parser.has_update:
        content += f'''#### PUT /api/v1/{module_name_kebab}/{basename}/{{id}}/

Update resource (full update).

**Request Body:**

```json
{{
  "name": "Updated Name",
  "description": "Updated description",
  "config": {{}}
}}
```

**Response:** `200 OK`

'''
    
    if viewset_parser.has_partial_update:
        content += f'''#### PATCH /api/v1/{module_name_kebab}/{basename}/{{id}}/

Update resource (partial update).

**Request Body:**

```json
{{
  "name": "Updated Name"
}}
```

**Response:** `200 OK`

'''
    
    if viewset_parser.has_destroy:
        content += f'''#### DELETE /api/v1/{module_name_kebab}/{basename}/{{id}}/

Delete resource.

**Response:** `204 No Content`

'''
    
    # Document custom actions
    for action in viewset_parser.custom_actions:
        for method in action['methods']:
            if method.upper() == 'OPTIONS':
                continue
            
            url = f'/api/v1/{module_name_kebab}/{basename}/{{id}}/{action["url_path"]}/' if action['detail'] else f'/api/v1/{module_name_kebab}/{basename}/{action["url_path"]}/'
            
            content += f'''#### {method.upper()} {url}

{action['docstring'] or f'Custom action: {action["name"]}'}

**Response:** `200 OK`

```json
{{
  "status": "success"
}}
```

'''
    
    content += '''
### Health Check

#### GET /api/v1/{module_name_kebab}/health/

Health check endpoint.

**Response:** `200 OK`

```json
{
  "status": "healthy",
  "module": "{module_name_kebab}",
  "checks": {
    "database": "ok",
    "cache": "ok",
    "module_model": {
      "status": "ok",
      "total_count": 0
    }
  }
}
```

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


def main():
    """Generate API documentation for all modules."""
    print("📚 Generating API documentation from ViewSets...\n")
    
    all_modules = []
    for batch_modules in MODULE_BATCHES.values():
        all_modules.extend(batch_modules)
    
    for module_name in all_modules:
        print(f"Processing {module_name}...")
        
        api_file = BACKEND_BASE / module_name / 'api.py'
        urls_file = BACKEND_BASE / module_name / 'urls.py'
        
        if not api_file.exists():
            print(f"   ⚠️  {api_file} not found")
            continue
        
        viewset_parser = parse_viewset(api_file)
        if not viewset_parser:
            print(f"   ⚠️  Could not parse ViewSet from {api_file}")
            continue
        
        basename = get_basename_from_urls(urls_file) if urls_file.exists() else 'resource'
        
        doc_content = generate_api_doc(module_name, viewset_parser, basename)
        
        # Write to documentation repo
        output_path = DOCS_BASE / module_name.replace('_', '-') / 'API.md'
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(doc_content)
        
        print(f"   ✅ Generated {output_path}")
    
    print("\n✅ All API documentation generated!")


if __name__ == '__main__':
    main()
