import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { BudgetForm, initialBudgetValue } from '../components/BudgetForm';
import { GovernedError, PageHeader, usePageTitle } from '../components/BudgetUI';
import { QUERY_KEYS, ROUTES } from '../contracts';
import { BudgetManagementApiError, budgetService } from '../services/budget-service';

export function CreateBudgetPage() { usePageTitle('Create budget'); const navigate = useNavigate(); const client = useQueryClient(); const mutation = useMutation({ mutationFn: budgetService.createBudget, onSuccess: (budget) => { void client.invalidateQueries({ queryKey: QUERY_KEYS.root }); toast.success('Draft created. Add allocations to make it usable.'); navigate(ROUTES.ALLOCATIONS(budget.id)); } }); const fieldErrors = mutation.error instanceof BudgetManagementApiError ? mutation.error.fieldErrors : undefined; return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Create budget" description="Start with the fiscal envelope. Allocation totals are derived by the server and cannot be entered here."/><Card className="max-w-4xl"><CardHeader><CardTitle>Planning details</CardTitle></CardHeader><CardContent><BudgetForm initial={initialBudgetValue()} serverErrors={fieldErrors} busy={mutation.isPending} submitLabel="Create and allocate" onCancel={() => navigate(ROUTES.BUDGETS)} onSubmit={(value) => mutation.mutate(value)}/></CardContent></Card>{mutation.error ? <GovernedError error={mutation.error}/> : null}</main>; }
