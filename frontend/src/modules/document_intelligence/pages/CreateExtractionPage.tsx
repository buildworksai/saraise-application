import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select';
import { ApiProblem, PageHeader } from '../components/ModuleShell';
import { deterministicKey, useUnsavedChanges } from '../components/module-utils';
import { DocumentIntelligenceApiError, documentIntelligenceService } from '../services/document-intelligence-service';
import type { DocumentExtractionCreateRequest, ExtractionEngine, ExtractionType } from '../contracts';

export function CreateExtractionPage() {
  const navigate = useNavigate();
  const [documentId, setDocumentId] = useState('');
  const [versionId, setVersionId] = useState('');
  const [engine, setEngine] = useState<ExtractionEngine>('tesseract');
  const [type, setType] = useState<ExtractionType>('text');
  const [templateId, setTemplateId] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const requiresTemplate = type === 'structured' || type === 'zone';
  const dirty = [documentId, versionId, templateId].some(Boolean);
  useUnsavedChanges(dirty && !submitted);
  const mutation = useMutation({
    mutationFn: (request: DocumentExtractionCreateRequest) => documentIntelligenceService.createExtraction(request),
    onSuccess: ({ extraction }) => { setSubmitted(true); navigate(`/document-intelligence/extractions/${extraction.id}`); },
  });
  const fieldErrors = mutation.error instanceof DocumentIntelligenceApiError ? mutation.error.detail.field_errors ?? [] : [];
  const errorFor = (field: string) => fieldErrors.find((error) => error.field === field)?.message;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    mutation.mutate({
      document_id: documentId.trim(), document_version_id: versionId.trim(), engine,
      extraction_type: type, template_id: templateId.trim() || undefined,
      idempotency_key: deterministicKey('extract', documentId, versionId, type, templateId || engine),
    });
  };
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader title="Process a document" description="Validate an immutable DMS version, reserve quota, and enqueue a durable evidence-producing extraction." actions={<Button variant="ghost" onClick={() => navigate('/document-intelligence/extractions')}><ArrowLeft className="mr-2 h-4 w-4" />Back</Button>} />
      {mutation.error && <ApiProblem error={mutation.error} onRetry={() => mutation.reset()} inline />}
      <Card className="mx-auto max-w-3xl p-6">
        <form className="space-y-5" onSubmit={submit} noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input id="document-id" label="DMS document UUID" required value={documentId} error={errorFor('document_id')} aria-describedby={errorFor('document_id') ? 'document-id-error' : undefined} onChange={(event) => setDocumentId(event.target.value)} />
            <Input id="version-id" label="Immutable version UUID" required value={versionId} error={errorFor('document_version_id')} onChange={(event) => setVersionId(event.target.value)} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div><label className="mb-1 block text-sm font-medium" htmlFor="extraction-type">Extraction type</label><Select value={type} onValueChange={(value: ExtractionType) => setType(value)}><SelectTrigger id="extraction-type"><SelectValue /></SelectTrigger><SelectContent>{['text', 'structured', 'table', 'zone'].map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select></div>
            <div><label className="mb-1 block text-sm font-medium" htmlFor="engine">Engine</label><Select value={engine} onValueChange={setEngine}><SelectTrigger id="engine"><SelectValue /></SelectTrigger><SelectContent>{['tesseract', 'aws_textract', 'azure_form_recognizer', 'google_vision'].map((value) => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select></div>
          </div>
          {requiresTemplate && <Input id="template-id" label="Extraction template UUID" required value={templateId} error={errorFor('template_id')} onChange={(event) => setTemplateId(event.target.value)} />}
          <div className="rounded-md border bg-muted/40 p-4 text-sm text-muted-foreground">The API verifies tenant ownership, MIME type, 50 MiB limit, provider readiness, concurrency, and quota before returning 202. No document bytes pass through this form.</div>
          <div className="flex justify-end"><Button type="submit" disabled={mutation.isPending || !documentId.trim() || !versionId.trim() || (requiresTemplate && !templateId.trim())} aria-busy={mutation.isPending}>{mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}{mutation.isPending ? 'Validating and queuing…' : 'Queue extraction'}</Button></div>
        </form>
      </Card>
    </main>
  );
}
