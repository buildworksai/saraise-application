import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import {
  GovernedError,
  Page,
  PageSkeleton,
  Surface,
  useUnsavedChanges,
} from '../components/EmailMarketingUI';
import {
  ROUTES,
  type EmailMarketingConfigurationDocument,
  type SuppressionReason,
  type SuppressionScope,
  type SuppressionSource,
} from '../contracts';
import { useEmailMarketingConfiguration } from '../hooks/use-email-marketing-configuration';
import {
  EMAIL_MARKETING_QUERY_KEYS,
  emailMarketingService,
} from '../services/email-marketing-service';

export function CreateSuppressionPage() {
  const configuration = useEmailMarketingConfiguration();
  if (configuration.isLoading) return <PageSkeleton label="Loading suppression configuration"/>;
  if (configuration.error) return <Page title="Add suppression" description="Suppressions override consent."><GovernedError error={configuration.error} retry={() => void configuration.refetch()}/></Page>;
  if (!configuration.data) return <Page title="Add suppression" description="Suppressions override consent."><GovernedError error={new Error('No governed suppression configuration was received.')} retry={() => void configuration.refetch()}/></Page>;
  const document = configuration.data.data.document;
  if (!document.compliance.suppression_scopes[0] || !document.compliance.suppression_reasons[0] || !document.compliance.suppression_sources[0]) {
    return <Page title="Add suppression" description="Suppressions override consent."><GovernedError error={new Error('Suppression allow-lists are empty; configuration must be corrected before recording evidence.')}/></Page>;
  }
  return <ConfiguredCreateSuppressionPage configuration={document}/>;
}

function ConfiguredCreateSuppressionPage({ configuration }: { readonly configuration: EmailMarketingConfigurationDocument }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [email, setEmail] = useState('');
  const [scope, setScope] = useState<SuppressionScope>(configuration.compliance.suppression_scopes[0]!);
  const [reason, setReason] = useState<SuppressionReason>(configuration.compliance.suppression_reasons[0]!);
  const [source, setSource] = useState<SuppressionSource>(configuration.compliance.suppression_sources[0]!);
  const [expires, setExpires] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');
  const dirty = Boolean(email || notes || expires);
  useUnsavedChanges(dirty);
  const mutation = useMutation({
    mutationFn: () => emailMarketingService.suppressions.create({
      email,
      scope,
      reason,
      source,
      expires_at: expires ? new Date(expires).toISOString() : null,
      notes,
    }),
    onSuccess: async (result) => {
      await client.invalidateQueries({ queryKey: EMAIL_MARKETING_QUERY_KEYS.all });
      navigate(ROUTES.SUPPRESSION_DETAIL(result.data.id));
    },
  });
  const permanent = configuration.compliance.permanent_suppression_reasons.includes(reason);
  const cls = 'mt-1 block w-full rounded-md border bg-background p-2';
  return <Page title="Add suppression" description="Suppressions override consent. Expiry availability follows the tenant compliance policy." back={{ label: 'Suppressions', to: ROUTES.SUPPRESSIONS }}>
    <form className="space-y-6" onSubmit={(event) => {
      event.preventDefault();
      if (!email.includes('@')) {
        setError('Enter a valid email address.');
        return;
      }
      if (permanent && expires) {
        setError(`${reason} suppressions cannot expire under the active policy.`);
        return;
      }
      setError('');
      mutation.mutate();
    }}>
      <Surface title="Suppression evidence">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-medium">Email<input aria-label="Suppressed email" type="email" required className={cls} value={email} onChange={(event) => setEmail(event.target.value)}/></label>
          <label className="text-sm font-medium">Scope<select aria-label="Suppression scope" className={cls} value={scope} onChange={(event) => setScope(event.target.value as SuppressionScope)}>{configuration.compliance.suppression_scopes.map((value) => <option key={value}>{value}</option>)}</select></label>
          <label className="text-sm font-medium">Reason<select aria-label="Suppression reason" className={cls} value={reason} onChange={(event) => {
            const next = event.target.value as SuppressionReason;
            setReason(next);
            if (configuration.compliance.permanent_suppression_reasons.includes(next)) setExpires('');
          }}>{configuration.compliance.suppression_reasons.map((value) => <option key={value}>{value}</option>)}</select></label>
          <label className="text-sm font-medium">Source<select aria-label="Suppression source" className={cls} value={source} onChange={(event) => setSource(event.target.value as SuppressionSource)}>{configuration.compliance.suppression_sources.map((value) => <option key={value}>{value}</option>)}</select></label>
          <label className="text-sm font-medium">Expires (optional)<input aria-label="Suppression expiry" type="datetime-local" disabled={permanent} className={cls} value={expires} onChange={(event) => setExpires(event.target.value)}/><span className="mt-1 block text-xs font-normal text-muted-foreground">{permanent ? `${reason} is configured as permanent.` : 'Optional expiry allowed by the active compliance policy.'}</span></label>
        </div>
        <label className="mt-4 block text-sm font-medium">Privileged audit notes<textarea aria-label="Suppression notes" className={cls} rows={4} value={notes} onChange={(event) => setNotes(event.target.value)}/></label>
      </Surface>
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      {mutation.error ? <GovernedError error={mutation.error}/> : null}
      <p className="sr-only" aria-live="polite">{mutation.isPending ? 'Recording suppression' : ''}</p>
      <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => {
        if (!dirty || window.confirm('Discard this suppression?')) navigate(ROUTES.SUPPRESSIONS);
      }}>Cancel</Button><Button disabled={mutation.isPending} type="submit">{mutation.isPending ? 'Recording…' : 'Record suppression'}</Button></div>
    </form>
  </Page>;
}
