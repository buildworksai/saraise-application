# Python Helper Functions

This file consolidates all Python helper functions from rule files.

## URL & Domain Helpers

See [python-url-helpers.py](python-url-helpers.py) for URL construction functions.

## Timeout & Duration Helpers

See [python-timeout-helpers.py](python-timeout-helpers.py) for timeout and duration configuration functions.

## Logging & Monitoring Helpers

See [python-logging-helpers.py](python-logging-helpers.py) for logging and monitoring configuration functions.

## File Path & Directory Helpers

See [python-path-helpers.py](python-path-helpers.py) for file path and directory helper functions.

## Usage

Import helper functions from their respective modules:

```python
from src.core.urls import get_api_url, get_frontend_url
from src.core.timeouts import get_session_timeout, get_api_timeout
from src.core.logging import get_log_level, get_monitoring_config
from src.core.paths import get_project_root, get_backend_dir
```

