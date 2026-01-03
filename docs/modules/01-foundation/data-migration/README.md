# Data Migration Framework Module

<!-- SPDX-License-Identifier: Apache-2.0 -->

The Data Migration Framework module provides intelligent data import/migration from external systems (CSV, Excel, JSON, SQL, API) with AI-powered field mapping, validation, deduplication, and rollback capabilities.

## Features

- **Multiple Source Formats**: CSV, Excel, JSON, SQL databases, REST/SOAP APIs
- **AI-Powered Field Mapping**: Intelligent field mapping with confidence scoring
- **Data Quality Validation**: MDM integration for data quality checks
- **Duplicate Detection**: AI-powered duplicate detection with MDM integration
- **Rollback & Recovery**: Transaction-based and snapshot-based rollback
- **Job Scheduling**: Scheduled and recurring migrations
- **Real-time Monitoring**: Progress tracking and performance metrics
- **Inter-Module Integration**: MDM, QMS, Workflow Automation
- **Customization**: Server scripts, client scripts, webhooks, event bus

## Quick Start

### Creating a Migration

```python
from src.modules.data_migration.services.migration_service import MigrationService

service = MigrationService(db)
migration = await service.create_migration(
    migration_name="Customer Import",
    target_resource_type="Customer",
    tenant_id=tenant_id,
    created_by=user_id,
)
```

### Uploading and Analyzing File

```python
migration = await service.upload_file(
    migration_id=migration.id,
    file=uploaded_file,
    tenant_id=tenant_id,
)
```

### Generating Field Mappings

```python
result = await service.analyze_and_map(
    migration_id=migration.id,
    tenant_id=tenant_id,
)
```

### Validating Data

```python
validation = await service.validate_migration(
    migration_id=migration.id,
    tenant_id=tenant_id,
)
```

### Executing Migration

```python
migration = await service.start_migration(
    migration_id=migration.id,
    tenant_id=tenant_id,
    dry_run=False,
)
```

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Features](FEATURES.md)
- [Data Model](DATA-MODEL.md)
- [API Specification](API-SPECIFICATION.md)
- [User Guide](USER-GUIDE.md)
- [Admin Guide](ADMIN-GUIDE.md)
- [Integrations](INTEGRATIONS.md)
- [Ask Amani Configuration](AGENT-CONFIGURATION.md)
- [Customization Guide](CUSTOMIZATION.md)
- [Demo Data](DEMO-DATA.md)

## Dependencies

- base
- auth
- metadata
- master_data_management

## Installation

The module is installed automatically when added to the module manifest.
