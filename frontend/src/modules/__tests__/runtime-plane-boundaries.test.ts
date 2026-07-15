/** Runtime-plane source guards for Control Plane ownership boundaries. */

import { describe, expect, it } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const MODULES_DIR = path.join(__dirname, '..');

const readSourceFiles = (moduleName: string): string => {
  const root = path.join(MODULES_DIR, moduleName);
  const files: string[] = [];

  const visit = (directory: string) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const entryPath = path.join(directory, entry.name);
      if (entry.isDirectory()) visit(entryPath);
      else if (/\.(ts|tsx)$/.test(entry.name) && !entry.name.endsWith('.test.ts')) files.push(entryPath);
    }
  };

  visit(root);
  return files.map((file) => fs.readFileSync(file, 'utf-8')).join('\n');
};

describe('runtime plane ownership boundaries', () => {
  it('keeps tenant management read-only', () => {
    const source = readSourceFiles('tenant_management');

    expect(source).not.toMatch(/apiClient\.(post|put|patch|delete)\s*\(/);
    expect(source).not.toContain('useMutation');
    expect(source).not.toMatch(/\b(CREATE|UPDATE|DELETE|SUSPEND|ACTIVATE|ENABLE|DISABLE)\s*:/);
  });

  it('keeps Control Plane platform APIs out of the application', () => {
    const source = readSourceFiles('platform_management');

    expect(source).not.toContain('/api/v1/platform');
    expect(source).not.toMatch(/apiClient\.(put|patch|delete)\s*\(/);
    expect(source.match(/apiClient\.post\s*\(/g) ?? []).toHaveLength(1);
    expect(source).toContain('ENDPOINTS.LICENSING.ACTIVATE');
  });
});
