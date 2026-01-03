/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: File Path & Directory Helper Functions
// frontend/src/helpers/path-helpers.ts
// Reference: docs/architecture/application-architecture.md § 6 (Deployment)

export const getPaths = () => {
  /**
   * CRITICAL: All paths must be environment-configured via Vite.
   * No hardcoded paths - use environment variables only.
   */
  return {
    projectRoot: import.meta.env.VITE_PROJECT_ROOT || '.',
    frontend: {
      dir: import.meta.env.VITE_FRONTEND_DIR || 'frontend',
      src: import.meta.env.VITE_FRONTEND_SRC_DIR || 'frontend/src',
      dist: import.meta.env.VITE_FRONTEND_DIST_DIR || 'frontend/dist',
      build: import.meta.env.VITE_FRONTEND_BUILD_DIR || 'frontend/build'
    },
    backend: {
      dir: import.meta.env.VITE_BACKEND_DIR || 'backend',
      src: import.meta.env.VITE_BACKEND_SRC_DIR || 'backend/src'
    },
    docker: {
      compose: import.meta.env.VITE_DOCKER_COMPOSE_FILE || 'docker-compose.yml'
    }
  };
};

export const getProjectRoot = (): string => {
  return getPaths().projectRoot;
};

export const getFrontendDir = (): string => {
  return getPaths().frontend.dir;
};

