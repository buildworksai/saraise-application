# Customization Guide for Data Migration Module

<!-- SPDX-License-Identifier: Apache-2.0 -->

This guide describes how to customize the Data Migration Framework module using server scripts, client scripts, webhooks, and event bus integration.

## Overview

The Data Migration module supports extensive customization through:

- **Server Scripts**: Custom Python code for data transformation and validation
- **Client Scripts**: Custom JavaScript for UI customization
- **Webhooks**: External notifications for migration events
- **Event Bus**: Integration with SARAISE event bus
- **Custom API Endpoints**: Extend the module with custom endpoints

## Server Scripts

Server scripts allow you to customize migration logic on the server side.

### Available Hook Points

1. **before_migration_validation**: Before validation runs
2. **after_migration_validation**: After validation completes
3. **before_field_mapping**: Before field mapping generation
4. **after_field_mapping**: After field mapping generation
5. **before_data_transformation**: Before data transformation
6. **after_data_transformation**: After data transformation
7. **before_migration_execution**: Before migration execution
8. **after_migration_execution**: After migration execution
9. **before_record_import**: Before each record import
10. **after_record_import**: After each record import
11. **on_migration_error**: When migration error occurs
12. **on_migration_complete**: When migration completes

### Example Server Script

```python
from src.modules.data_migration.hooks import register_server_script

async def custom_validation(context, db):
    """Custom validation before migration"""
    migration_id = context.get("migration_id")
    source_data = context.get("source_data", [])

    # Add custom validation logic
    for record in source_data:
        if not record.get("email"):
            raise ValueError("Email is required")

    return None

# Register the script
register_server_script("before_migration_validation", custom_validation)
```

### AI-Powered Script Generation

Ask Amani can generate server scripts:

```
User: "Create a server script that validates email format before migration"
Ask Amani: Generates Python code for email validation
```

## Client Scripts

Client scripts allow you to customize the migration UI.

### Available Hook Points

1. **on_migration_form_load**: When migration form loads
2. **on_migration_form_save**: When migration form is saved
3. **on_file_upload**: When file is uploaded
4. **on_field_mapping_change**: When field mapping changes
5. **on_validation_complete**: When validation completes
6. **on_migration_start**: When migration starts
7. **on_migration_progress**: When migration progress updates
8. **on_migration_complete**: When migration completes
9. **on_migration_error**: When migration error occurs

### Example Client Script

```javascript
// Custom validation on form load
frappe.ui.form.on('Data Migration', {
    refresh: function(frm) {
        // Add custom button
        if (frm.doc.status === 'Draft') {
            frm.add_custom_button('Custom Action', function() {
                frappe.msgprint('Custom action executed');
            });
        }
    },

    file_upload: function(frm) {
        // Custom file processing
        console.log('File uploaded:', frm.doc.file_name);
    }
});
```

## Webhooks

Webhooks allow external systems to be notified of migration events.

### Supported Events

- **migration_started**: Migration execution started
- **migration_completed**: Migration execution completed
- **migration_failed**: Migration execution failed
- **migration_progress**: Migration progress update
- **validation_complete**: Validation completed
- **record_imported**: Record successfully imported
- **migration_rolled_back**: Migration rolled back

### Registering Webhooks

```python
from src.modules.data_migration.hooks import register_webhook

# Register webhook for migration completion
register_webhook(
    event_name="migration_completed",
    url="https://example.com/webhooks/migration-complete",
    method="POST",
    headers={"Authorization": "Bearer token"},
    secret="webhook_secret",
)
```

### Webhook Payload

```json
{
    "event": "migration_completed",
    "migration_id": "abc123",
    "tenant_id": "tenant123",
    "success_count": 100,
    "error_count": 5,
    "timestamp": "2025-01-20T10:00:00Z"
}
```

## Event Bus Integration

The module publishes events to the SARAISE event bus.

### Published Events

1. **migration_started**: When migration starts
2. **migration_completed**: When migration completes
3. **migration_failed**: When migration fails
4. **migration_progress**: Progress updates

### Subscribing to Events

```python
from src.core.event_bus import subscribe

async def handle_migration_complete(event):
    """Handle migration completion event"""
    migration_id = event.data.get("migration_id")
    print(f"Migration {migration_id} completed")

# Subscribe to event
subscribe("data_migration.migration_completed", handle_migration_complete)
```

## Custom API Endpoints

You can extend the module with custom API endpoints.

### Example Custom Endpoint

```python
from rest_framework import routers
from src.modules.data_migration.views import DataMigrationViewSet

# Add custom route
router = routers.DefaultRouter()
router.register(r'custom', DataMigrationViewSet, basename='data-migration')
@router.post("/custom-endpoint")
async def custom_endpoint():
    """Custom endpoint for data migration"""
    return {"message": "Custom endpoint"}
```

## Workflow Customization

You can customize migration workflows using the Workflow Automation module.

### Example Workflow Customization

1. Add approval gates
2. Custom error handling
3. Notification steps
4. Custom validation steps

## Best Practices

1. **Use Server Scripts for Business Logic**: Keep complex logic on the server
2. **Use Client Scripts for UI**: Enhance user experience with client scripts
3. **Use Webhooks for Integration**: Connect with external systems via webhooks
4. **Use Events for Loose Coupling**: Subscribe to events for decoupled integration
5. **Test Customizations**: Always test customizations in a development environment

## AI-Powered Customization

Ask Amani can help generate customization code:

- "Create a server script that validates phone numbers"
- "Add a webhook for migration completion"
- "Create a client script that shows custom progress indicator"
- "Generate event handler for migration failures"

## Examples

### Example 1: Custom Data Transformation

```python
async def custom_transformation(context, db):
    """Transform data before import"""
    transformed_data = context.get("transformed_data", [])

    for record in transformed_data:
        # Custom transformation logic
        if "full_name" in record:
            parts = record["full_name"].split(" ", 1)
            record["first_name"] = parts[0]
            record["last_name"] = parts[1] if len(parts) > 1 else ""
            del record["full_name"]

    return {"transformed_data": transformed_data}

register_server_script("after_data_transformation", custom_transformation)
```

### Example 2: Custom Validation

```python
async def custom_validation(context, db):
    """Custom validation rules"""
    source_data = context.get("source_data", [])
    errors = []

    for idx, record in enumerate(source_data):
        # Custom validation
        if record.get("age") and int(record["age"]) < 18:
            errors.append({
                "row": idx + 1,
                "field": "age",
                "error": "Age must be 18 or older"
            })

    if errors:
        context["validation_errors"] = errors

    return context

register_server_script("before_migration_validation", custom_validation)
```

### Example 3: Webhook Integration

```python
# Register webhook
register_webhook(
    event_name="migration_completed",
    url="https://api.example.com/migrations/complete",
    method="POST",
    headers={"X-API-Key": "your-api-key"},
)

# Webhook will be automatically triggered when migration completes
```
