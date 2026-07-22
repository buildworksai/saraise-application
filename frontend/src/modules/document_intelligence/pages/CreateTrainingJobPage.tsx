import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { ApiProblem, PageHeader, PageSkeleton } from '../components/ModuleShell';
import { deterministicKey, stableFingerprint, useUnsavedChanges } from '../components/module-utils';
import { DocumentIntelligenceApiError, documentIntelligenceService } from '../services/document-intelligence-service';
import type { ClassifierTrainingJobCreateRequest, TrainingItem } from '../contracts';
import { useDocumentIntelligenceConfiguration } from '../hooks/use-document-intelligence-configuration';
import { DOCUMENT_INTELLIGENCE_PATHS } from '../paths';

function parseItems(value: string, minimumTotal: number, minimumPerCategory: number): { items: readonly TrainingItem[]; errors: readonly string[] } {
  const errors: string[] = [];
  const items = value.split('\n').map((line) => line.trim()).filter(Boolean).flatMap((line, index) => {
    const [documentId, versionId, category, ...extra] = line.split(',').map((part) => part.trim());
    if (!documentId || !versionId || !category || extra.length > 0) { errors.push(`Line ${index + 1} must contain document UUID, version UUID, and category.`); return []; }
    return [{ document_id: documentId, document_version_id: versionId, category }];
  });
  if (items.length < minimumTotal) errors.push(`${minimumTotal - items.length} more training examples are required.`);
  const counts = new Map<string, number>(); items.forEach((item) => counts.set(item.category, (counts.get(item.category) ?? 0) + 1));
  counts.forEach((count, category) => { if (count < minimumPerCategory) errors.push(`Category ${category} needs ${minimumPerCategory - count} more examples.`); });
  return { items, errors };
}

// The workflow keeps parsing, tenant policy validation, and durable submission visible in one form boundary.
// eslint-disable-next-line complexity
export function CreateTrainingJobPage() {
  const navigate = useNavigate();
  const configuration = useDocumentIntelligenceConfiguration();
  const [name, setName] = useState(''); const [version, setVersion] = useState(''); const [source, setSource] = useState(''); const [attempted, setAttempted] = useState(false); const [submitted, setSubmitted] = useState(false);
  useUnsavedChanges(!submitted && Boolean(name || version || source));
  const parsed = parseItems(source, configuration.data?.document.classifier.minimum_training_documents ?? Number.POSITIVE_INFINITY, configuration.data?.document.classifier.minimum_documents_per_category ?? Number.POSITIVE_INFINITY);
  const mutation = useMutation({ mutationFn: (request: ClassifierTrainingJobCreateRequest) => documentIntelligenceService.createTrainingJob(request), onSuccess: ({ training_job: job }) => { setSubmitted(true); navigate(DOCUMENT_INTELLIGENCE_PATHS.TRAINING.DETAIL(job.id)); } });
  const submit = (event: FormEvent) => { event.preventDefault(); setAttempted(true); if (!name.trim() || !version.trim() || parsed.errors.length > 0) return; mutation.mutate({ name: name.trim(), requested_version: version.trim(), items: parsed.items, idempotency_key: deterministicKey('train', version, String(parsed.items.length), stableFingerprint(source)) }); };
  const fieldErrors = mutation.error instanceof DocumentIntelligenceApiError ? mutation.error.detail.field_errors ?? [] : [];
  if (configuration.isLoading) return <PageSkeleton table={false} />;
  if (configuration.error || !configuration.data) return <main className="p-4 sm:p-8"><ApiProblem error={configuration.error} onRetry={() => { void configuration.refetch(); }} /></main>;
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Train tenant classifier" description={`Training requires at least ${configuration.data.document.classifier.minimum_training_documents} immutable DMS versions and ${configuration.data.document.classifier.minimum_documents_per_category} examples for every represented category.`} actions={<Button variant="ghost" onClick={() => navigate(DOCUMENT_INTELLIGENCE_PATHS.TRAINING.LIST)}><ArrowLeft className="mr-2 h-4 w-4" />Back</Button>} />{mutation.error && <ApiProblem error={mutation.error} onRetry={() => mutation.reset()} inline />}<Card className="mx-auto max-w-4xl p-6"><form className="space-y-5" onSubmit={submit}><div className="grid gap-4 sm:grid-cols-2"><Input id="training-name" label="Training job name" required value={name} error={fieldErrors.find((error) => error.field === 'name')?.message} onChange={(event) => setName(event.target.value)} /><Input id="requested-version" label="Requested model version" required value={version} error={fieldErrors.find((error) => error.field === 'requested_version')?.message} onChange={(event) => setVersion(event.target.value)} /></div><Textarea id="training-items" label="Training examples" className="min-h-72 font-mono text-xs" placeholder="document_uuid, version_uuid, category_slug" required value={source} error={fieldErrors.find((error) => error.field === 'training_items')?.message} onChange={(event) => setSource(event.target.value)} /><p className="text-xs text-muted-foreground">One example per line: document UUID, immutable version UUID, category slug. Duplicates and cross-tenant versions are rejected by the service.</p>{attempted && parsed.errors.length > 0 && <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive" role="alert">{parsed.errors.map((error) => <p key={error}>{error}</p>)}</div>}<div className="flex items-center justify-between gap-4"><p className="text-sm text-muted-foreground">{parsed.items.length} validated rows · {new Set(parsed.items.map((item) => item.category)).size} categories</p><Button type="submit" disabled={mutation.isPending || !name.trim() || !version.trim()} aria-busy={mutation.isPending}>{mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}{mutation.isPending ? 'Validating and queuing…' : 'Queue training'}</Button></div></form></Card></main>;
}
