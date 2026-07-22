/* eslint-disable complexity, max-lines-per-function */
import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Calculator, Edit, Trash2 } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Dialog } from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Skeleton } from '@/components/ui/Skeleton';
import { useAuthStore } from '@/stores/auth-store';
import { ROUTES } from '../contracts';
import {
  EmptyPanel,
  formatAmount,
  formatDate,
  PageHeader,
  PageSkeleton,
  ProblemState,
  StatusPill,
  titleCase,
} from '../components/AssetManagementUI';
import { assetQueryKeys, assetService } from '../services/asset-service';

const PAGE_SIZE = 12;

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-words text-sm">{value}</dd>
    </div>
  );
}

export const AssetDetailPage = () => {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const tenantId = useAuthStore((state) => state.user?.tenant_id ?? null);
  const [historyPage, setHistoryPage] = useState(1);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState('');
  const [calculateOpen, setCalculateOpen] = useState(false);
  const [entryDate, setEntryDate] = useState(new Date().toISOString().slice(0, 10));

  const assetQuery = useQuery({
    queryKey: assetQueryKeys.asset(tenantId, id),
    queryFn: () => assetService.getAsset(id),
    enabled: Boolean(id),
  });
  const historyFilters = { asset_id: id, ordering: '-entry_date', page: historyPage, page_size: PAGE_SIZE };
  const historyQuery = useQuery({
    queryKey: assetQueryKeys.depreciation(tenantId, historyFilters),
    queryFn: () => assetService.listDepreciationEntries(historyFilters),
    enabled: Boolean(id),
  });
  const deleteMutation = useMutation({
    mutationFn: () => assetService.deleteAsset(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: assetQueryKeys.root(tenantId) });
      toast.success('Asset archived');
      navigate(ROUTES.ASSETS.LIST);
    },
  });
  const calculateMutation = useMutation({
    mutationFn: () => assetService.calculateDepreciation(id, { entry_date: entryDate }),
    onSuccess: (entry) => {
      setHistoryPage(1);
      setCalculateOpen(false);
      void queryClient.invalidateQueries({ queryKey: assetQueryKeys.root(tenantId) });
      toast.success(`Depreciation recorded for ${formatDate(entry.entry_date)}`);
    },
  });

  if (assetQuery.isLoading) return <PageSkeleton />;
  if (assetQuery.error || !assetQuery.data) {
    return <main className="p-4 sm:p-8"><ProblemState error={assetQuery.error ?? new Error('Asset unavailable')} onRetry={() => void assetQuery.refetch()} /></main>;
  }

  const asset = assetQuery.data;
  const canDepreciate = asset.is_active
    && asset.depreciation_method !== 'none'
    && asset.useful_life_years !== null
    && Number(asset.current_value) > Number(asset.residual_value);
  const depreciationUnavailableReason = !asset.is_active
    ? 'Inactive assets cannot receive new depreciation entries.'
    : asset.depreciation_method === 'none'
      ? 'This asset has no depreciation method.'
      : asset.useful_life_years === null
        ? 'A useful life is required before depreciation can be calculated.'
        : 'The asset is already at its residual value.';

  const submitDepreciation = (event: FormEvent) => {
    event.preventDefault();
    if (entryDate) calculateMutation.mutate();
  };

  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title={`${asset.asset_code} · ${asset.asset_name}`}
        description={`${titleCase(asset.category)} · acquired ${formatDate(asset.purchase_date)}`}
        backLabel="Asset register"
        onBack={() => navigate(ROUTES.ASSETS.LIST)}
        actions={(
          <>
            <StatusPill active={asset.is_active} />
            <Button variant="secondary" onClick={() => navigate(ROUTES.ASSETS.EDIT(asset.id))}>
              <Edit className="mr-2 h-4 w-4" aria-hidden="true" />
              Edit
            </Button>
            <span title={canDepreciate ? undefined : depreciationUnavailableReason}>
              <Button
                disabled={!canDepreciate}
                onClick={() => {
                  setEntryDate((current) => current < asset.purchase_date ? asset.purchase_date : current);
                  setCalculateOpen(true);
                }}
              >
                <Calculator className="mr-2 h-4 w-4" aria-hidden="true" />
                Calculate depreciation
              </Button>
            </span>
            <Button variant="danger" onClick={() => setDeleteOpen(true)}>
              <Trash2 className="mr-2 h-4 w-4" aria-hidden="true" />
              Archive
            </Button>
          </>
        )}
      />

      <section className="grid gap-4 sm:grid-cols-3" aria-label="Asset value summary">
        <Card className="p-5">
          <p className="text-sm text-muted-foreground">Purchase cost</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{formatAmount(asset.purchase_cost)}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-muted-foreground">Current value</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{formatAmount(asset.current_value)}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-muted-foreground">Residual value</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{formatAmount(asset.residual_value)}</p>
        </Card>
      </section>

      <Card className="p-5 sm:p-6">
        <h2 className="text-lg font-semibold">Asset information</h2>
        <dl className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Asset code" value={asset.asset_code} />
          <Field label="Category" value={titleCase(asset.category)} />
          <Field label="Purchase date" value={formatDate(asset.purchase_date)} />
          <Field label="Location" value={asset.location || 'Not specified'} />
          <Field label="Depreciation method" value={titleCase(asset.depreciation_method)} />
          <Field label="Useful life" value={asset.useful_life_years ? `${asset.useful_life_years} years` : 'Not applicable'} />
          <Field
            label="Declining balance rate"
            value={asset.declining_balance_rate ? `${formatAmount(asset.declining_balance_rate)}% annually` : 'Not applicable'}
          />
          <Field label="Last updated" value={new Date(asset.updated_at).toLocaleString()} />
        </dl>
        {!canDepreciate && <p className="mt-5 border-t pt-4 text-sm text-muted-foreground">{depreciationUnavailableReason}</p>}
      </Card>

      <section className="space-y-3" aria-labelledby="depreciation-history-heading">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 id="depreciation-history-heading" className="text-lg font-semibold">Depreciation history</h2>
            <p className="text-sm text-muted-foreground">Append-only calculations recorded by the server.</p>
          </div>
          {historyQuery.data && <p className="text-sm text-muted-foreground">{historyQuery.data.count} entries</p>}
        </div>
        {historyQuery.isLoading ? (
          <Card className="space-y-2 p-4" aria-label="Loading depreciation history" aria-busy="true">
            {Array.from({ length: 4 }, (_, index) => <Skeleton key={index} className="h-12 w-full" />)}
          </Card>
        ) : historyQuery.error ? (
          <ProblemState error={historyQuery.error} onRetry={() => void historyQuery.refetch()} compact />
        ) : !historyQuery.data?.items.length ? (
          <EmptyPanel
            title="No depreciation recorded"
            description={canDepreciate
              ? 'Calculate the first period when its entry date is due.'
              : depreciationUnavailableReason}
            action={canDepreciate ? {
              label: 'Calculate depreciation',
              onClick: () => {
                setEntryDate((current) => current < asset.purchase_date ? asset.purchase_date : current);
                setCalculateOpen(true);
              },
            } : undefined}
          />
        ) : (
          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[680px] text-sm">
                <caption className="sr-only">Depreciation entries for {asset.asset_name}</caption>
                <thead className="bg-muted text-left">
                  <tr>
                    {['Entry date', 'Depreciation', 'Accumulated', 'Book value', 'Recorded'].map((heading) => (
                      <th key={heading} scope="col" className="px-4 py-3 font-medium">{heading}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {historyQuery.data.items.map((entry) => (
                    <tr key={entry.id} className="border-t">
                      <td className="px-4 py-3 font-medium">{formatDate(entry.entry_date)}</td>
                      <td className="px-4 py-3 tabular-nums">{formatAmount(entry.depreciation_amount)}</td>
                      <td className="px-4 py-3 tabular-nums">{formatAmount(entry.accumulated_depreciation)}</td>
                      <td className="px-4 py-3 font-medium tabular-nums">{formatAmount(entry.book_value)}</td>
                      <td className="px-4 py-3 text-muted-foreground">{new Date(entry.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <nav className="flex items-center justify-between border-t p-4" aria-label="Depreciation history pagination">
              <p className="text-sm text-muted-foreground">Page {historyPage}</p>
              <div className="flex gap-2">
                <Button variant="secondary" disabled={!historyQuery.data.previous} onClick={() => setHistoryPage((page) => Math.max(page - 1, 1))}>Previous</Button>
                <Button variant="secondary" disabled={!historyQuery.data.next} onClick={() => setHistoryPage((page) => page + 1)}>Next</Button>
              </div>
            </nav>
          </Card>
        )}
      </section>

      <Dialog
        open={calculateOpen}
        onOpenChange={(open) => {
          setCalculateOpen(open);
          if (!open) calculateMutation.reset();
        }}
        title="Calculate depreciation"
        description="The server calculates and persists one immutable entry. Duplicate or out-of-order dates are rejected."
      >
        <form className="space-y-4" onSubmit={submitDepreciation}>
          <Input
            id="depreciation-entry-date"
            label="Entry date"
            type="date"
            required
            min={asset.purchase_date}
            value={entryDate}
            onChange={(event) => setEntryDate(event.target.value)}
          />
          {calculateMutation.error && <ProblemState error={calculateMutation.error} compact />}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setCalculateOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={!entryDate || calculateMutation.isPending}>
              {calculateMutation.isPending ? 'Calculating…' : 'Calculate and record'}
            </Button>
          </div>
        </form>
      </Dialog>

      <Dialog
        open={deleteOpen}
        onOpenChange={(open) => {
          setDeleteOpen(open);
          if (!open) {
            setDeleteConfirmation('');
            deleteMutation.reset();
          }
        }}
        title="Archive asset"
        description="This removes the asset from the operational register without deleting its protected depreciation history."
      >
        <div className="space-y-4">
          <Input
            id="delete-asset-confirmation"
            label={`Type ${asset.asset_code} to confirm`}
            autoComplete="off"
            value={deleteConfirmation}
            onChange={(event) => setDeleteConfirmation(event.target.value)}
          />
          {deleteMutation.error && <ProblemState error={deleteMutation.error} compact />}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setDeleteOpen(false)}>Cancel</Button>
            <Button
              variant="danger"
              disabled={deleteConfirmation !== asset.asset_code || deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
            >
              {deleteMutation.isPending ? 'Archiving…' : 'Archive asset'}
            </Button>
          </div>
        </div>
      </Dialog>
    </main>
  );
};
