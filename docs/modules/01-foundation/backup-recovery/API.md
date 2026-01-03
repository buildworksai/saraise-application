# API Documentation - Backup & Recovery

**Base Path:** `/api/v1/backup`

## REST Endpoints

### Create Backup
```http
POST /api/v1/backup/create
{
  "backup_type": "full",
  "description": "Monthly backup"
}
```

### List Backups
```http
GET /api/v1/backup/list?page=1&limit=20
```

### Restore Backup
```http
POST /api/v1/backup/{id}/restore
{
  "target_timestamp": "2025-12-11T00:00:00Z"
}
```

### Schedule Backup
```http
POST /api/v1/backup/schedule
{
  "frequency": "daily",
  "time": "02:00",
  "retention_days": 30
}
```

---
**Related:** [README](./README.md) | [Technical Specs](./TECHNICAL_SPECIFICATIONS.md)
