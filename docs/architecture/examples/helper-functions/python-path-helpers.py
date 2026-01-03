# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: File Path & Directory Helper Functions
# backend/src/helpers/path_helpers.py
# Reference: docs/architecture/operational-runbooks.md § 1.1

import os
from pathlib import Path

def get_project_root() -> Path:
    """Get project root directory.
    
    CRITICAL: All file operations must use project-relative paths.
    See docs/architecture/operational-runbooks.md § 1.1.
    """
    return Path(os.getenv('PROJECT_ROOT', '.'))

def get_backend_dir() -> Path:
    """Get backend directory"""
    return get_project_root() / os.getenv('BACKEND_DIR', 'backend')

def get_frontend_dir() -> Path:
    """Get frontend directory"""
    return get_project_root() / os.getenv('FRONTEND_DIR', 'frontend')

def get_backend_src_dir() -> Path:
    """Get backend source directory"""
    return get_backend_dir() / os.getenv('BACKEND_SRC_DIR', 'src')

def get_frontend_src_dir() -> Path:
    """Get frontend source directory"""
    return get_frontend_dir() / os.getenv('FRONTEND_SRC_DIR', 'src')

def get_docker_compose_file() -> Path:
    """Get Docker Compose file path"""
    return get_project_root() / os.getenv('DOCKER_COMPOSE_FILE', 'docker-compose.yml')

def get_database_data_dir() -> Path:
    """Get database data directory"""
    return get_project_root() / os.getenv('DB_DATA_DIR', 'data/postgres')

def get_logs_dir() -> Path:
    """Get logs directory"""
    return get_project_root() / os.getenv('LOGS_DIR', 'logs')

def get_paths_config() -> dict:
    """Get all path configuration as dictionary"""
    return {
        'project_root': str(get_project_root()),
        'backend': {
            'dir': str(get_backend_dir()),
            'src': str(get_backend_src_dir()),
            'tests': str(get_backend_dir() / os.getenv('BACKEND_TESTS_DIR', 'tests')),
            'logs': str(get_backend_dir() / os.getenv('BACKEND_LOGS_DIR', 'logs'))
        },
        'frontend': {
            'dir': str(get_frontend_dir()),
            'src': str(get_frontend_src_dir()),
            'dist': str(get_frontend_dir() / os.getenv('FRONTEND_DIST_DIR', 'dist')),
            'build': str(get_frontend_dir() / os.getenv('FRONTEND_BUILD_DIR', 'build'))
        },
        'docker': {
            'compose': str(get_docker_compose_file()),
            'backend_volume': os.getenv('DOCKER_VOLUME_BACKEND', './backend:/app'),
            'frontend_volume': os.getenv('DOCKER_VOLUME_FRONTEND', './frontend:/app')
        },
        'data': {
            'postgres': str(get_database_data_dir()),
            'redis': str(get_project_root() / os.getenv('REDIS_DATA_DIR', 'data/redis')),
            'minio': str(get_project_root() / os.getenv('MINIO_DATA_DIR', 'data/minio')),
            'vault': str(get_project_root() / os.getenv('VAULT_DATA_DIR', 'data/vault'))
        }
    }

