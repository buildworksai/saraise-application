import type { UUID } from './contracts';

const ROOT = '/document-intelligence' as const;

export const DOCUMENT_INTELLIGENCE_PATHS = {
  EXTRACTIONS: {
    LIST: `${ROOT}/extractions`,
    CREATE: `${ROOT}/extractions/new`,
    DETAIL: (id: UUID) => `${ROOT}/extractions/${encodeURIComponent(id)}` as const,
  },
  CLASSIFICATIONS: {
    LIST: `${ROOT}/classifications`,
    DETAIL: (id: UUID) => `${ROOT}/classifications/${encodeURIComponent(id)}` as const,
  },
  TEMPLATES: {
    LIST: `${ROOT}/templates`,
    CREATE: `${ROOT}/templates/new`,
    DETAIL: (id: UUID) => `${ROOT}/templates/${encodeURIComponent(id)}` as const,
    EDIT: (id: UUID) => `${ROOT}/templates/${encodeURIComponent(id)}/edit` as const,
  },
  TRAINING: {
    LIST: `${ROOT}/training`,
    CREATE: `${ROOT}/training/new`,
    DETAIL: (id: UUID) => `${ROOT}/training/${encodeURIComponent(id)}` as const,
  },
  CONFIGURATION: `${ROOT}/configuration`,
  HEALTH: `${ROOT}/health`,
} as const;
