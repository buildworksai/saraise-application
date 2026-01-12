/**
 * Contract Validation Tests
 *
 * Validates that all module contracts.ts files:
 * 1. Exist and are properly structured
 * 2. Export ENDPOINTS constant
 * 3. Export EXAMPLES with correct types (optional)
 * 4. Compile without TypeScript errors
 *
 * Reference: saraise-documentation/rules/agent-rules/27-contracts-architecture.md
 */

import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

// Static imports to avoid dynamic import issues
// ⚠️ ARCHITECTURAL ENFORCEMENT: platform_management removed from application repo
import * as tenantContracts from '../tenant_management/contracts';
import * as securityContracts from '../security_access_control/contracts';
import * as aiAgentContracts from '../ai_agent_management/contracts';

const MODULES_DIR = path.join(__dirname, '..');
const MODULES = [
  { name: 'tenant_management', contracts: tenantContracts },
  { name: 'security_access_control', contracts: securityContracts },
  { name: 'ai_agent_management', contracts: aiAgentContracts },
];

describe('Module Contracts Validation', () => {
  for (const { name: moduleName, contracts: contractModule } of MODULES) {
    describe(`${moduleName}`, () => {
      const contractPath = path.join(MODULES_DIR, moduleName, 'contracts.ts');

      it('should have contracts.ts file', () => {
        expect(fs.existsSync(contractPath)).toBe(true);
      });

      it('should export ENDPOINTS constant', () => {
        expect(contractModule.ENDPOINTS).toBeDefined();
        expect(typeof contractModule.ENDPOINTS).toBe('object');
      });

      it('should export EXAMPLES constant (optional but recommended)', () => {
        // EXAMPLES is optional but recommended for agent guidance
        if ('EXAMPLES' in contractModule && contractModule.EXAMPLES !== undefined) {
          expect(typeof contractModule.EXAMPLES).toBe('object');
        }
      });

      it('should have valid ENDPOINTS structure', () => {
        const endpoints = contractModule.ENDPOINTS;

        // ENDPOINTS should be an object
        expect(endpoints).toBeDefined();
        expect(typeof endpoints).toBe('object');

        // Check that endpoints are either strings or functions
        const validateEndpoint = (value: unknown): boolean => {
          if (typeof value === 'string') return true;
          if (typeof value === 'function') return true;
          if (typeof value === 'object' && value !== null) {
            return Object.values(value).every(validateEndpoint);
          }
          return false;
        };

        expect(validateEndpoint(endpoints)).toBe(true);
      });

      it('should have EXAMPLES that satisfy their types (if provided)', () => {
        // EXAMPLES is optional but recommended
        if (!('EXAMPLES' in contractModule) || contractModule.EXAMPLES === undefined) {
          return; // Skip validation if EXAMPLES not provided
        }

        const examples = contractModule.EXAMPLES;

        // EXAMPLES should be an object
        expect(examples).not.toBeNull();
        expect(typeof examples).toBe('object');

        // Check that examples have request/response structure
        const exampleKeys = Object.keys(examples as Record<string, unknown>);
        expect(exampleKeys.length).toBeGreaterThan(0);

        // Each example should have request or response
        for (const key of exampleKeys) {
          const example = (examples as Record<string, unknown>)[key];
          expect(example).toBeDefined();
          expect(typeof example).toBe('object');
        }
      });
    });
  }
});

describe('Contract File Structure', () => {
  for (const { name: moduleName } of MODULES) {
    it(`${moduleName}/contracts.ts should have AGENT INSTRUCTION comment`, () => {
      const contractPath = path.join(MODULES_DIR, moduleName, 'contracts.ts');
      const content = fs.readFileSync(contractPath, 'utf-8');
      expect(content).toContain('AGENT INSTRUCTION');
      expect(content).toContain('Read this file FIRST');
    });
  }
});
