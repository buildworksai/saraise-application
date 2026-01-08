#!/usr/bin/env npx ts-node
/**
 * SARAISE Typed API Client Generator
 *
 * This script generates a fully-typed API client from the OpenAPI schema.
 * The generated client provides:
 *   - Type-safe API calls with correct request/response types
 *   - No hardcoded URLs - all endpoints are centralized
 *   - IntelliSense/autocomplete support in editors
 *
 * Usage:
 *   npx ts-node scripts/generate-typed-client.ts
 *
 * Output:
 *   frontend/src/lib/api-client-generated.ts
 */

import * as fs from 'fs';
import * as path from 'path';
import * as yaml from 'js-yaml';

interface OpenAPIPath {
  get?: OpenAPIOperation;
  post?: OpenAPIOperation;
  put?: OpenAPIOperation;
  patch?: OpenAPIOperation;
  delete?: OpenAPIOperation;
}

interface OpenAPIOperation {
  operationId?: string;
  summary?: string;
  description?: string;
  requestBody?: {
    content?: {
      'application/json'?: {
        schema?: { $ref?: string };
      };
    };
  };
  responses?: {
    [code: string]: {
      content?: {
        'application/json'?: {
          schema?: { $ref?: string; items?: { $ref?: string } };
        };
      };
    };
  };
}

interface OpenAPISpec {
  paths: { [path: string]: OpenAPIPath };
  components?: {
    schemas?: { [name: string]: unknown };
  };
}

// Module configuration
const MODULES = [
  {
    prefix: '/api/v1/platform/',
    name: 'platform',
    displayName: 'Platform Management',
  },
  {
    prefix: '/api/v1/tenant-management/',
    name: 'tenantManagement',
    displayName: 'Tenant Management',
  },
  {
    prefix: '/api/v1/security/',
    name: 'security',
    displayName: 'Security & Access Control',
  },
  {
    prefix: '/api/v1/ai-agents/',
    name: 'aiAgents',
    displayName: 'AI Agent Management',
  },
  {
    prefix: '/api/v1/auth/',
    name: 'auth',
    displayName: 'Authentication',
  },
];

function extractTypeName(ref: string | undefined): string | null {
  if (!ref) return null;
  // Extract from "#/components/schemas/TypeName"
  const match = ref.match(/#\/components\/schemas\/(\w+)/);
  return match ? match[1] : null;
}

function getResponseType(operation: OpenAPIOperation): string {
  const successCodes = ['200', '201'];
  for (const code of successCodes) {
    const response = operation.responses?.[code];
    const content = response?.content?.['application/json'];
    if (content?.schema) {
      const ref = content.schema.$ref;
      const itemsRef = content.schema.items?.$ref;
      
      if (ref) {
        const typeName = extractTypeName(ref);
        return typeName ? `components['schemas']['${typeName}']` : 'unknown';
      }
      if (itemsRef) {
        const typeName = extractTypeName(itemsRef);
        return typeName ? `components['schemas']['${typeName}'][]` : 'unknown[]';
      }
    }
  }
  // Check for 204 No Content
  if (operation.responses?.['204']) {
    return 'void';
  }
  return 'unknown';
}

function getRequestType(operation: OpenAPIOperation): string | null {
  const content = operation.requestBody?.content?.['application/json'];
  const ref = content?.schema?.$ref;
  if (ref) {
    const typeName = extractTypeName(ref);
    return typeName ? `components['schemas']['${typeName}']` : null;
  }
  return null;
}

function pathToFunctionName(path: string, method: string): string {
  // Remove /api/v1/ prefix and trailing slash
  let cleanPath = path.replace(/^\/api\/v1\//, '').replace(/\/$/, '');
  
  // Handle path parameters
  cleanPath = cleanPath.replace(/\{(\w+)\}/g, 'By$1');
  
  // Convert to camelCase
  const parts = cleanPath.split('/').filter(Boolean);
  const name = parts
    .map((part, index) => {
      part = part.replace(/-/g, '_');
      if (index === 0) return part;
      return part.charAt(0).toUpperCase() + part.slice(1);
    })
    .join('');
  
  // Add method prefix
  const methodPrefix = {
    get: 'get',
    post: 'create',
    put: 'update',
    patch: 'patch',
    delete: 'delete',
  }[method] || method;
  
  return methodPrefix + name.charAt(0).toUpperCase() + name.slice(1);
}

function generateClient(spec: OpenAPISpec): string {
  const lines: string[] = [];
  
  // Header
  lines.push(`/**
 * SARAISE Typed API Client
 *
 * AUTO-GENERATED from backend/schema.yml
 * DO NOT EDIT MANUALLY - run 'npx ts-node scripts/generate-typed-client.ts'
 *
 * This client provides type-safe API calls with:
 * - Correct request/response types from OpenAPI schema
 * - No hardcoded URLs
 * - Full IntelliSense support
 *
 * Usage:
 *   import { platformApi } from '@/lib/api-client-generated';
 *   const settings = await platformApi.settings.list();
 */

import { apiClient } from '@/services/api-client';
import type { components } from '@/types/api';
`);

  // Generate module-specific clients
  for (const module of MODULES) {
    const modulePaths: { [key: string]: string[] } = {};
    
    // Group paths by resource
    for (const [pathUrl, pathDef] of Object.entries(spec.paths)) {
      if (!pathUrl.startsWith(module.prefix)) continue;
      
      const relativePath = pathUrl.slice(module.prefix.length);
      const resourceName = relativePath.split('/')[0];
      
      if (!modulePaths[resourceName]) {
        modulePaths[resourceName] = [];
      }
      
      for (const method of ['get', 'post', 'put', 'patch', 'delete'] as const) {
        const operation = pathDef[method];
        if (!operation) continue;
        
        const responseType = getResponseType(operation);
        const requestType = getRequestType(operation);
        const hasPathParam = pathUrl.includes('{');
        
        let functionDef: string;
        
        if (hasPathParam && method === 'get') {
          // Detail endpoint
          functionDef = `    get: (id: string) => apiClient.get<${responseType}>(\`${pathUrl.replace('{id}', '${id}')}\`),`;
        } else if (hasPathParam && method === 'delete') {
          functionDef = `    delete: (id: string) => apiClient.delete<${responseType}>(\`${pathUrl.replace('{id}', '${id}')}\`),`;
        } else if (hasPathParam && (method === 'put' || method === 'patch')) {
          const reqType = requestType || 'unknown';
          functionDef = `    update: (id: string, data: ${reqType}) => apiClient.${method}<${responseType}>(\`${pathUrl.replace('{id}', '${id}')}\`, data),`;
        } else if (!hasPathParam && method === 'get') {
          // List endpoint
          functionDef = `    list: () => apiClient.get<${responseType}>('${pathUrl}'),`;
        } else if (!hasPathParam && method === 'post') {
          const reqType = requestType || 'unknown';
          functionDef = `    create: (data: ${reqType}) => apiClient.post<${responseType}>('${pathUrl}', data),`;
        } else {
          continue;
        }
        
        modulePaths[resourceName].push(functionDef);
      }
    }
    
    if (Object.keys(modulePaths).length === 0) continue;
    
    lines.push(`
/**
 * ${module.displayName} API
 */
export const ${module.name}Api = {`);
    
    for (const [resource, methods] of Object.entries(modulePaths)) {
      if (methods.length === 0) continue;
      lines.push(`  ${resource}: {`);
      lines.push(...methods);
      lines.push('  },');
    }
    
    lines.push('} as const;');
  }

  // Add unified export
  lines.push(`
/**
 * Unified API client with all modules
 */
export const api = {
${MODULES.filter(m => Object.keys(spec.paths).some(p => p.startsWith(m.prefix))).map(m => `  ${m.name}: ${m.name}Api,`).join('\n')}
} as const;
`);

  return lines.join('\n');
}

async function main() {
  const schemaPath = path.resolve(__dirname, '../backend/schema.yml');
  const outputPath = path.resolve(__dirname, '../frontend/src/lib/api-client-generated.ts');
  
  console.log('SARAISE Typed API Client Generator');
  console.log('===================================');
  console.log('');
  
  // Check if schema exists
  if (!fs.existsSync(schemaPath)) {
    console.error(`ERROR: Schema file not found at ${schemaPath}`);
    console.error('Run "./scripts/sync-api-contracts.sh" first to generate the schema.');
    process.exit(1);
  }
  
  console.log(`Reading schema from: ${schemaPath}`);
  const schemaContent = fs.readFileSync(schemaPath, 'utf-8');
  const spec = yaml.load(schemaContent) as OpenAPISpec;
  
  console.log(`Found ${Object.keys(spec.paths).length} API paths`);
  console.log('');
  
  console.log('Generating typed client...');
  const client = generateClient(spec);
  
  // Ensure output directory exists
  const outputDir = path.dirname(outputPath);
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }
  
  fs.writeFileSync(outputPath, client);
  console.log(`Generated: ${outputPath}`);
  console.log('');
  console.log('✓ Typed API client generated successfully');
}

main().catch(console.error);

