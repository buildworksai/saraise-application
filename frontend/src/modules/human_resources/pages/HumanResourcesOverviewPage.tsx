import { useQuery } from '@tanstack/react-query'; import { Link } from 'react-router-dom';
import { Building2, CalendarCheck, HeartPulse, Palmtree, Users } from 'lucide-react'; import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { ROUTES, hrKeys } from '../contracts'; import { hrService } from '../services/hr-service'; import { GovernedError, PageShell, PageSkeleton, StatusChip } from '../components/hr-ui';
export function HumanResourcesOverviewPage() {
  const employees = useQuery({ queryKey: hrKeys.employees({ page: 1, page_size: 1 }), queryFn: () => hrService.listEmployees({ page: 1, page_size: 1 }) });
  const departments = useQuery({ queryKey: hrKeys.departments({ page: 1, page_size: 1 }), queryFn: () => hrService.listDepartments({ page: 1, page_size: 1 }) });
  const attendance = useQuery({ queryKey: hrKeys.attendances({ page: 1, page_size: 1, ordering: '-attendance_date' }), queryFn: () => hrService.listAttendances({ page: 1, page_size: 1, ordering: '-attendance_date' }) });
  const leave = useQuery({ queryKey: hrKeys.leaveRequests({ page: 1, page_size: 1, status: 'pending' }), queryFn: () => hrService.listLeaveRequests({ page: 1, page_size: 1, status: 'pending' }) });
  const health = useQuery({ queryKey: hrKeys.health, queryFn: hrService.getHealth, retry: false });
  const queries = [employees, departments, attendance, leave]; if (queries.some((query) => query.isLoading)) return <PageSkeleton cards={4} />;
  const failed = queries.find((query) => query.error); if (failed?.error) return <PageShell title="Human Resources" description="Your tenant's people operations control centre."><GovernedError error={failed.error} retry={() => { queries.forEach((query) => void query.refetch()); }} resource="HR overview" /></PageShell>;
  const cards = [
    { label: 'Employees', value: employees.data?.pagination.count ?? 0, path: ROUTES.EMPLOYEES, icon: Users, detail: 'Lifecycle and reporting lines' },
    { label: 'Departments', value: departments.data?.pagination.count ?? 0, path: ROUTES.DEPARTMENTS, icon: Building2, detail: 'Organizational structure' },
    { label: 'Attendance records', value: attendance.data?.pagination.count ?? 0, path: ROUTES.ATTENDANCE, icon: CalendarCheck, detail: 'Clock and manual evidence' },
    { label: 'Pending leave', value: leave.data?.pagination.count ?? 0, path: ROUTES.LEAVE, icon: Palmtree, detail: 'Requests awaiting action' },
  ];
  return <PageShell title="Human Resources" description="Trusted employee records, organizational structure, attendance, and leave—without invented payroll or performance data." actions={health.data ? <StatusChip status={health.data.data.status} /> : <span className="inline-flex items-center text-sm text-muted-foreground"><HeartPulse className="mr-2 h-4 w-4" />Readiness unavailable</span>}>
    <section aria-label="Human Resources summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{cards.map(({ label, value, path, icon: Icon, detail }) => <Link key={label} to={path} className="rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><Card className="h-full transition hover:border-primary/50 hover:shadow-sm"><CardHeader className="flex-row items-center justify-between pb-2"><CardTitle className="text-sm font-medium">{label}</CardTitle><Icon className="h-5 w-5 text-primary" /></CardHeader><CardContent><p className="text-3xl font-bold">{value}</p><p className="mt-1 text-xs text-muted-foreground">{detail}</p></CardContent></Card></Link>)}</section>
    <Card><CardHeader><CardTitle>Open-source HR core</CardTitle></CardHeader><CardContent className="grid gap-4 text-sm text-muted-foreground md:grid-cols-3"><p><strong className="block text-foreground">Tenant isolated</strong>Every record is scoped by policy and database isolation.</p><p><strong className="block text-foreground">Audit ready</strong>Lifecycle and leave actions preserve transition evidence.</p><p><strong className="block text-foreground">Extensible by events</strong>Paid payroll, recruitment, and learning modules integrate without patching employee records.</p></CardContent></Card>
  </PageShell>;
}
