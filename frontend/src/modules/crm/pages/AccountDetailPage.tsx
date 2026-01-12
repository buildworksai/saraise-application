/**
 * Account Detail Page
 *
 * Displays account details with hierarchy view.
 */
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { AccountHierarchyTree } from '../components/AccountHierarchyTree';
import { crmService } from '../services/crm-service';

export const AccountDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: account, isLoading, error } = useQuery({
    queryKey: ['crm-account', id],
    queryFn: () => (id ? crmService.getAccount(id) : Promise.reject(new Error('No ID'))),
    enabled: !!id,
  });

  const { data: hierarchy } = useQuery({
    queryKey: ['crm-account-hierarchy', id],
    queryFn: () => (id ? crmService.getAccountHierarchy(id) : Promise.reject(new Error('No ID'))),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-muted rounded w-1/4"></div>
          <div className="h-64 bg-muted rounded"></div>
        </div>
      </div>
    );
  }

  if (error || !account) {
    return (
      <div className="p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-foreground mb-4">Account not found</h2>
          <Button onClick={() => navigate('/crm/accounts')}>Back to Accounts</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" onClick={() => navigate('/crm/accounts')}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
          <h1 className="text-3xl font-bold text-foreground">{account.name}</h1>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Account Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Name</label>
                  <p className="text-sm font-medium">{account.name}</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Type</label>
                  <div className="mt-1">
                    <StatusBadge status={account.account_type === 'customer' ? 'active' : 'inactive'} />
                  </div>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Industry</label>
                  <p className="text-sm">{account.industry || '-'}</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Website</label>
                  <p className="text-sm">{account.website || '-'}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
        <div className="space-y-6">
          {hierarchy && <AccountHierarchyTree hierarchy={hierarchy} />}
        </div>
      </div>
    </div>
  );
};
