import { describe, expect, it } from 'vitest';
import { buildTenantSidebarTree, getTenantRouteValidationIssues, tenantRoutes as discoveredRoutes } from '@/navigation/tenant-route-registry';
import { tenantRoutes as budgetRoutes } from './routes';

describe('budget management tenant routes', () => {
  it('discovers every required sidebar and contextual route', () => {
    const discovered = discoveredRoutes.filter((route) => route.module === 'budget_management');
    expect(discovered.map((route) => route.path)).toEqual(expect.arrayContaining(['/budget-management/budgets','/budget-management/approvals','/budget-management/variance','/budget-management/report','/budget-management/budgets/new','/budget-management/budgets/:id','/budget-management/budgets/:id/edit','/budget-management/budgets/:id/allocations']));
    expect(discovered).toHaveLength(budgetRoutes.length);
  });
  it('publishes unique valid paths and parents', () => { expect(new Set(budgetRoutes.map((route) => route.path)).size).toBe(budgetRoutes.length); expect(getTenantRouteValidationIssues(budgetRoutes)).toEqual([]); });
  it('keeps sidebar leaves in parity with sidebar descriptors', () => { const tree=buildTenantSidebarTree(budgetRoutes); expect(tree).toHaveLength(1); expect(tree[0]?.children.map((leaf)=>leaf.routeId)).toEqual(budgetRoutes.filter((route)=>route.navigation.type==='sidebar').map((route)=>route.id)); });
});
