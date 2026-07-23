import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { GovernedError, Page, PageSkeleton, Surface, useUnsavedChanges } from '../components/EmailMarketingUI';
import { ROUTES, type ConsentLawfulBasis, type ConsentSource, type ConsentStatus, type EmailMarketingConfigurationDocument } from '../contracts';
import { useEmailMarketingConfiguration } from '../hooks/use-email-marketing-configuration';
import { EMAIL_MARKETING_QUERY_KEYS, emailMarketingService } from '../services/email-marketing-service';

export function RecordConsentPage() {
  const configuration = useEmailMarketingConfiguration();
  if (configuration.isLoading) return <PageSkeleton label="Loading consent configuration"/>;
  if (configuration.error) return <Page title="Record consent evidence" description="Append trusted consent evidence."><GovernedError error={configuration.error} retry={() => void configuration.refetch()}/></Page>;
  if (!configuration.data) return <Page title="Record consent evidence" description="Append trusted consent evidence."><GovernedError error={new Error('No governed consent configuration was received.')} retry={() => void configuration.refetch()}/></Page>;
  const document = configuration.data.data.document;
  if (!document.compliance.consent_sources[0] || !document.compliance.consent_lawful_bases[0]) {
    return <Page title="Record consent evidence" description="Append trusted consent evidence."><GovernedError error={new Error('Consent allow-lists are empty; configuration must be corrected before recording evidence.')}/></Page>;
  }
  return <ConfiguredRecordConsentPage configuration={document}/>;
}

function ConfiguredRecordConsentPage({ configuration }: { readonly configuration: EmailMarketingConfigurationDocument }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [email, setEmail] = useState('');
  const [purpose, setPurpose] = useState(configuration.defaults.consent_purpose);
  const [status, setStatus] = useState<ConsentStatus>(configuration.compliance.consent_required_status);
  const [basis, setBasis] = useState<ConsentLawfulBasis>(configuration.compliance.consent_lawful_bases[0]!);
  const [source, setSource] = useState<ConsentSource>(configuration.compliance.consent_sources[0]!);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const dirty = Boolean(email || notice);
  useUnsavedChanges(dirty);
  const mutation = useMutation({
    mutationFn: () => emailMarketingService.consents.create({
      email,
      purpose,
      status,
      lawful_basis: basis,
      source,
      notice_version: notice,
    }),
    onSuccess: async (result) => {
      await client.invalidateQueries({ queryKey: EMAIL_MARKETING_QUERY_KEYS.all });
      navigate(ROUTES.CONSENT_DETAIL(result.data.id));
    },
  });
  const cls = 'mt-1 block w-full rounded-md border bg-background p-2';
  return <Page title="Record consent evidence" description="Append a grant or revocation. Capture time and trusted request evidence are derived by the server." back={{ label: 'Consent history', to: ROUTES.CONSENTS }}>
    <form className="space-y-6" onSubmit={(event) => {
      event.preventDefault();
      if (!email.includes('@') || !purpose.trim() || !notice.trim()) {
        setError('Email, purpose, and notice version are required.');
        return;
      }
      setError('');
      mutation.mutate();
    }}>
      <Surface title="Immutable consent event" description="Network evidence, actor, and capture time cannot be supplied or spoofed by the browser."><div className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm font-medium">Email<input aria-label="Consent email" type="email" required className={cls} value={email} onChange={(event) => setEmail(event.target.value)}/></label>
        <label className="text-sm font-medium">Purpose<input aria-label="Consent purpose" required className={cls} value={purpose} onChange={(event) => setPurpose(event.target.value)}/></label>
        <label className="text-sm font-medium">Status<select aria-label="Consent status" className={cls} value={status} onChange={(event) => setStatus(event.target.value as ConsentStatus)}><option value="granted">Granted</option><option value="revoked">Revoked</option></select></label>
        <label className="text-sm font-medium">Lawful basis<select aria-label="Lawful basis" className={cls} value={basis} onChange={(event) => setBasis(event.target.value as ConsentLawfulBasis)}>{configuration.compliance.consent_lawful_bases.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label className="text-sm font-medium">Source<select aria-label="Consent source" className={cls} value={source} onChange={(event) => setSource(event.target.value as ConsentSource)}>{configuration.compliance.consent_sources.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label className="text-sm font-medium">Notice version<input aria-label="Notice version" required className={cls} value={notice} onChange={(event) => setNotice(event.target.value)}/></label>
      </div></Surface>
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      {mutation.error ? <GovernedError error={mutation.error}/> : null}
      <p className="sr-only" aria-live="polite">{mutation.isPending ? 'Appending consent evidence' : ''}</p>
      <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => {
        if (!dirty || window.confirm('Discard this consent event?')) navigate(ROUTES.CONSENTS);
      }}>Cancel</Button><Button disabled={mutation.isPending} type="submit">{mutation.isPending ? 'Appending…' : 'Append consent event'}</Button></div>
    </form>
  </Page>;
}
