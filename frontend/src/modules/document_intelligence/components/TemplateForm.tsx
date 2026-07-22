import { useState, type FormEvent } from 'react';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { ZoneEditor } from './ZoneEditor';
import { validateZones } from './zone-utils';
import { useUnsavedChanges } from './module-utils';
import type { DocumentIntelligenceConfigurationDocument, ExtractionEngine, ExtractionTemplateCreateRequest, ExtractionTemplateZoneInput } from '../contracts';

export type TemplateFormValue = ExtractionTemplateCreateRequest;

export function TemplateForm({ initial, configuration, pending, serverError, submitLabel, onSubmit }: { initial?: TemplateFormValue; configuration: DocumentIntelligenceConfigurationDocument; pending: boolean; serverError?: string; submitLabel: string; onSubmit: (value: TemplateFormValue) => Promise<void> }) {
  const defaults = initial ?? { name: '', description: '', document_category: '', engine: configuration.templates.default_engine, match_threshold: configuration.templates.default_match_threshold.toFixed(configuration.editor.coordinate_precision), zones: [] };
  const [name, setName] = useState(defaults.name);
  const [description, setDescription] = useState(defaults.description);
  const [category, setCategory] = useState(defaults.document_category);
  const [engine, setEngine] = useState<ExtractionEngine>(defaults.engine);
  const [threshold, setThreshold] = useState(defaults.match_threshold);
  const [zones, setZones] = useState<readonly ExtractionTemplateZoneInput[]>(defaults.zones);
  const [submitted, setSubmitted] = useState(false);
  useUnsavedChanges(!submitted && Boolean(name || description || category || zones.length));
  const issues = validateZones(zones);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (issues.length > 0 || !name.trim()) return;
    await onSubmit({ name: name.trim(), description: description.trim(), document_category: category.trim(), engine, match_threshold: Number(threshold).toFixed(4), zones });
    setSubmitted(true);
  };
  return <form className="space-y-6" onSubmit={(event) => { void submit(event); }}><div className="grid gap-4 sm:grid-cols-2"><Input id="template-name" label="Template name" required value={name} onChange={(event) => setName(event.target.value)} /><Input id="template-category" label="Document category (optional)" value={category} onChange={(event) => setCategory(event.target.value)} /><div><label htmlFor="template-engine" className="mb-1 block text-sm font-medium">OCR engine</label><select id="template-engine" className="w-full rounded-md border bg-background p-2" value={engine} onChange={(event) => setEngine(event.target.value)}>{configuration.providers.allowed_ocr_engines.map((value) => <option key={value}>{value}</option>)}</select></div><Input id="template-threshold" label="Match threshold" type="number" min="0" max="1" step={configuration.editor.coordinate_snap} required value={threshold} onChange={(event) => setThreshold(event.target.value)} /><div className="sm:col-span-2"><Textarea id="template-description" label="Description" value={description} onChange={(event) => setDescription(event.target.value)} /></div></div><ZoneEditor zones={zones} configuration={configuration} onChange={setZones} />{serverError && <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive" role="alert">{serverError}</p>}<div className="flex justify-end"><Button type="submit" disabled={pending || !name.trim() || issues.length > 0} aria-busy={pending}>{pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}{pending ? `${submitLabel}…` : submitLabel}</Button></div></form>;
}
