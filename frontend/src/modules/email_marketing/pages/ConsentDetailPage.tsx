import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { Detail, DetailGrid, formatDate, GovernedError, Page, PageSkeleton, Status, Surface } from '../components/EmailMarketingUI';
import { ROUTES, type ConsentSource } from '../contracts';
import { useEmailMarketingConfiguration } from '../hooks/use-email-marketing-configuration';
import { EMAIL_MARKETING_QUERY_KEYS, emailMarketingService } from '../services/email-marketing-service';

export function ConsentDetailPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const configuration = useEmailMarketingConfiguration();
  const sources = configuration.data?.data.document.compliance.consent_sources;
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState<ConsentSource | ''>('');
  useEffectForConfiguredSource(sources, source, setSource);
  const query = useQuery({ queryKey: EMAIL_MARKETING_QUERY_KEYS.consent(id), queryFn: () => emailMarketingService.consents.get(id), enabled: Boolean(id) });
  const revoke = useMutation({
    mutationFn: () => {
      if (!query.data || !source) throw new Error('Consent evidence or configured revocation source is unavailable.');
      return emailMarketingService.consents.revoke({ email: query.data.data.email, purpose: query.data.data.purpose, source, notice_version: query.data.data.notice_version });
    },
    onSuccess: async (result) => {
      await client.invalidateQueries({ queryKey: EMAIL_MARKETING_QUERY_KEYS.all });
      setOpen(false);
      navigate(ROUTES.CONSENT_DETAIL(result.data.id));
    },
  });
  if (configuration.isLoading || query.isLoading) return <PageSkeleton label="Loading consent evidence"/>;
  if (configuration.error || query.error) return <Page title="Consent evidence" description="Append-only compliance history."><GovernedError error={configuration.error ?? query.error} retry={() => { void configuration.refetch(); void query.refetch(); }}/></Page>;
  if (!configuration.data || !query.data) return <Page title="Consent evidence" description="Append-only compliance history."><GovernedError error={new Error('No governed consent response was received.')} retry={() => { void configuration.refetch(); void query.refetch(); }}/></Page>;
  const item = query.data.data;
  return <Page title={item.email} description="Immutable consent event and redacted evidence chain." back={{ label: 'Consent history', to: ROUTES.CONSENTS }} actions={item.status === 'granted' ? <Button variant="danger" onClick={() => setOpen(true)}>Revoke consent</Button> : undefined}>
    <Surface title="Consent evidence"><DetailGrid><Detail label="Status"><Status value={item.status}/></Detail><Detail label="Purpose">{item.purpose}</Detail><Detail label="Lawful basis">{item.lawful_basis}</Detail><Detail label="Source">{item.source}</Detail><Detail label="Notice">{item.notice_version}</Detail><Detail label="Captured">{formatDate(item.captured_at)}</Detail><Detail label="Actor">{item.actor_id ?? 'system'}</Detail><Detail label="Supersedes">{item.supersedes_id ?? 'Initial event'}</Detail></DetailGrid></Surface>
    <Surface title="Immutable history contract"><p className="text-sm">This record cannot be edited or deleted. Sensitive request evidence is not exposed by this operational API. A revocation appends a new event and immediately changes send eligibility.</p></Surface>
    <Dialog open={open} onOpenChange={setOpen} title="Revoke marketing consent" description="This appends a revocation and prevents subsequent sends after the eligibility recheck."><label className="text-sm font-medium">Revocation source<select aria-label="Revocation source" className="mt-1 block w-full rounded-md border bg-background p-2" value={source} onChange={(event) => setSource(event.target.value as ConsentSource)}>{configuration.data.data.document.compliance.consent_sources.map((value) => <option key={value}>{value}</option>)}</select></label>{revoke.error ? <GovernedError error={revoke.error}/> : null}<div className="mt-4 flex justify-end gap-2"><Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button><Button variant="danger" disabled={!source || revoke.isPending} onClick={() => revoke.mutate()}>{revoke.isPending ? 'Revoking…' : 'Append revocation'}</Button></div></Dialog>
  </Page>;
}

function useEffectForConfiguredSource(
  sources: readonly ConsentSource[] | undefined,
  source: ConsentSource | '',
  setSource: (value: ConsentSource) => void,
): void {
  useEffect(() => {
    const first = sources?.[0];
    if (!source && first) setSource(first);
  }, [sources, source, setSource]);
}
