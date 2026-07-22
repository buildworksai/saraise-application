import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Plus, Search } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { ROUTES, hrKeys } from '../contracts';
import type { EmployeeFilters, EmploymentStatus } from '../contracts';
import { hrService } from '../services/hr-service';
import { can, EmptyPanel, GovernedError, PageShell, PageSkeleton, Pagination, StatusChip } from '../components/hr-ui';

// eslint-disable-next-line complexity -- this page coordinates filters, pagination, permissions, and table states.
export function EmployeeListPage() {
  const navigate = useNavigate(); const [params, setParams] = useSearchParams();
  const filters: EmployeeFilters = { page: Number(params.get('page') ?? 1), page_size: 25,
    search: params.get('search') ?? undefined, employment_status: (params.get('status') ?? undefined) as EmploymentStatus | undefined,
    ordering: (params.get('ordering') ?? 'employee_number') as EmployeeFilters['ordering'] };
  const query = useQuery({ queryKey: hrKeys.employees(filters), queryFn: () => hrService.listEmployees(filters) });
  const update = (key: string, value: string) => { const next = new URLSearchParams(params); if (value) next.set(key, value); else next.delete(key); if (key !== 'page') next.set('page', '1'); setParams(next); };
  if (query.isLoading) return <PageSkeleton rows={7} />;
  if (query.error) return <PageShell title="Employees" description="Tenant-safe employee lifecycle records."><GovernedError error={query.error} retry={() => void query.refetch()} resource="Employees" /></PageShell>;
  const result = query.data;
  return <PageShell title="Employees" description="Search staff, inspect reporting relationships, and govern lifecycle changes."
    actions={result && can(result.capabilities, 'hr.employee:create') ? <Button onClick={() => navigate(ROUTES.EMPLOYEE_CREATE)} className="min-h-11"><Plus className="mr-2 h-4 w-4" />New employee</Button> : null}>
    <section aria-label="Employee filters" className="grid gap-3 rounded-xl border bg-card p-4 sm:grid-cols-3">
      <div className="relative"><Search className="absolute left-3 top-3.5 h-4 w-4 text-muted-foreground" /><Input aria-label="Search employees" className="pl-9" placeholder="Name, number, or email" value={filters.search ?? ''} onChange={(event) => update('search', event.target.value)} /></div>
      <select aria-label="Employment status" className="min-h-11 rounded-md border bg-background px-3" value={filters.employment_status ?? ''} onChange={(event) => update('status', event.target.value)}><option value="">All statuses</option>{['active', 'on_leave', 'inactive', 'terminated'].map((item) => <option key={item}>{item}</option>)}</select>
      <select aria-label="Employee ordering" className="min-h-11 rounded-md border bg-background px-3" value={filters.ordering} onChange={(event) => update('ordering', event.target.value)}><option value="employee_number">Employee number</option><option value="last_name">Last name</option><option value="-hire_date">Newest hires</option><option value="hire_date">Oldest hires</option></select>
    </section>
    {!result?.items.length ? <EmptyPanel title="No employees found" description={filters.search || filters.employment_status ? 'Change or clear the filters to broaden the result.' : result?.capabilities.length ? 'Create the first employee when your access policy allows it.' : 'Creation is unavailable until access policy returns an explicit capability decision.'} action={result && can(result.capabilities, 'hr.employee:create') ? { label: 'Create employee', onClick: () => navigate(ROUTES.EMPLOYEE_CREATE) } : undefined} />
      : <section className="overflow-hidden rounded-xl border bg-card"><div className="overflow-x-auto"><table className="w-full min-w-[850px] text-sm"><thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"><tr><th className="px-4 py-3">Employee</th><th className="px-4 py-3">Position</th><th className="px-4 py-3">Department</th><th className="px-4 py-3">Manager</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Hired</th></tr></thead><tbody className="divide-y">{result.items.map((employee) => <tr key={employee.id} className="hover:bg-muted/30"><td className="px-4 py-4"><Link className="font-semibold text-primary hover:underline focus-visible:ring-2" to={ROUTES.EMPLOYEE_DETAIL(employee.id)}>{employee.full_name || `${employee.first_name} ${employee.last_name}`}</Link><span className="block text-xs text-muted-foreground">{employee.employee_number} · {employee.email}</span></td><td className="px-4 py-4">{employee.position || 'Not assigned'}</td><td className="px-4 py-4">{employee.department_name ?? 'Unassigned'}</td><td className="px-4 py-4">{employee.manager_name ?? 'No manager'}</td><td className="px-4 py-4"><StatusChip status={employee.employment_status} /></td><td className="px-4 py-4">{employee.hire_date}</td></tr>)}</tbody></table></div><Pagination page={result.pagination.page} totalPages={result.pagination.total_pages} onPage={(page) => update('page', String(page))} /></section>}
  </PageShell>;
}
