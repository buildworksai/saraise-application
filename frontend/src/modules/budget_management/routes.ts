import { lazy } from 'react';
import { BarChart3, ClipboardCheck, FileSpreadsheet, WalletCards } from 'lucide-react';
import type { TenantRoute } from '@/navigation/tenant-route-types';

const modes = ['development', 'self-hosted', 'saas'] as const;
const parentRouteId = 'budget-management.budgets.list';
const contextual = { type: 'contextual' as const, parentRouteId };
export const tenantRoutes = [
  { id: parentRouteId, module: 'budget_management', path: '/budget-management/budgets', sourceFile: 'modules/budget_management/pages/BudgetListPage.tsx', Page: lazy(() => import('./pages/BudgetListPage').then(({ BudgetListPage }) => ({ default: BudgetListPage }))), modes, navigation: { type: 'sidebar', label: 'Budgets', icon: WalletCards, order: 8100 } },
  { id: 'budget-management.approvals.list', module: 'budget_management', path: '/budget-management/approvals', sourceFile: 'modules/budget_management/pages/ApprovalQueuePage.tsx', Page: lazy(() => import('./pages/ApprovalQueuePage').then(({ ApprovalQueuePage }) => ({ default: ApprovalQueuePage }))), modes, navigation: { type: 'sidebar', label: 'Budget approvals', icon: ClipboardCheck, order: 8101 } },
  { id: 'budget-management.variance.dashboard', module: 'budget_management', path: '/budget-management/variance', sourceFile: 'modules/budget_management/pages/VarianceDashboardPage.tsx', Page: lazy(() => import('./pages/VarianceDashboardPage').then(({ VarianceDashboardPage }) => ({ default: VarianceDashboardPage }))), modes, navigation: { type: 'sidebar', label: 'Budget variance', icon: BarChart3, order: 8102 } },
  { id: 'budget-management.report', module: 'budget_management', path: '/budget-management/report', sourceFile: 'modules/budget_management/pages/BudgetReportPage.tsx', Page: lazy(() => import('./pages/BudgetReportPage').then(({ BudgetReportPage }) => ({ default: BudgetReportPage }))), modes, navigation: { type: 'sidebar', label: 'Budget report', icon: FileSpreadsheet, order: 8103 } },
  { id: 'budget-management.budgets.create', module: 'budget_management', path: '/budget-management/budgets/new', sourceFile: 'modules/budget_management/pages/CreateBudgetPage.tsx', Page: lazy(() => import('./pages/CreateBudgetPage').then(({ CreateBudgetPage }) => ({ default: CreateBudgetPage }))), modes, navigation: contextual },
  { id: 'budget-management.budgets.detail', module: 'budget_management', path: '/budget-management/budgets/:id', sourceFile: 'modules/budget_management/pages/BudgetDetailPage.tsx', Page: lazy(() => import('./pages/BudgetDetailPage').then(({ BudgetDetailPage }) => ({ default: BudgetDetailPage }))), modes, navigation: contextual },
  { id: 'budget-management.budgets.edit', module: 'budget_management', path: '/budget-management/budgets/:id/edit', sourceFile: 'modules/budget_management/pages/EditBudgetPage.tsx', Page: lazy(() => import('./pages/EditBudgetPage').then(({ EditBudgetPage }) => ({ default: EditBudgetPage }))), modes, navigation: contextual },
  { id: 'budget-management.budgets.allocations', module: 'budget_management', path: '/budget-management/budgets/:id/allocations', sourceFile: 'modules/budget_management/pages/AllocationEditPage.tsx', Page: lazy(() => import('./pages/AllocationEditPage').then(({ AllocationEditPage }) => ({ default: AllocationEditPage }))), modes, navigation: contextual },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
