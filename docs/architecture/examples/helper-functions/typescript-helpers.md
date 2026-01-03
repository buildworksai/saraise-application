# TypeScript Helper Functions

This file consolidates all TypeScript helper functions from rule files.

## URL & Domain Helpers

See [typescript-url-helpers.ts](typescript-url-helpers.ts) for URL construction functions.

## Timeout & Duration Helpers

See [typescript-timeout-helpers.ts](typescript-timeout-helpers.ts) for timeout and duration configuration functions.

## Logging & Monitoring Helpers

See [typescript-logging-helpers.ts](typescript-logging-helpers.ts) for logging and monitoring configuration functions.

## File Path & Directory Helpers

See [typescript-path-helpers.ts](typescript-path-helpers.ts) for file path and directory helper functions.

## Usage

Import helper functions from their respective modules:

```typescript
import { getApiUrl, getFrontendUrl } from '@/lib/urls'
import { getTimeouts, getToastDuration } from '@/lib/timeouts'
import { getLogLevel, getMonitoringConfig } from '@/lib/logging'
import { getPaths, getProjectRoot } from '@/lib/paths'
```

