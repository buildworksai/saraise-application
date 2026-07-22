import { Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import type { DocumentMetadata, Folder, JsonPrimitive, UUID } from '../contracts';

export function FolderSelector({ folders, value, onChange, label = 'Folder', exclude }: { readonly folders: readonly Folder[]; readonly value: UUID | null; readonly onChange: (value: UUID | null) => void; readonly label?: string; readonly exclude?: UUID }) {
  return <label className="block text-sm font-medium">{label}<select className="mt-1 block w-full rounded-md border bg-background px-3 py-2" value={value ?? ''} onChange={(event) => onChange(event.target.value || null)}><option value="">Documents (root)</option>{folders.filter((folder) => folder.id !== exclude).map((folder) => <option key={folder.id} value={folder.id}>{'— '.repeat(folder.depth)}{folder.name}</option>)}</select></label>;
}

export function TagEditor({ value, onChange }: { readonly value: readonly string[]; readonly onChange: (value: readonly string[]) => void }) {
  return <Input id="document-tags" label="Tags" value={value.join(', ')} placeholder="contract, finance, signed" onChange={(event) => onChange([...new Set(event.target.value.split(',').map((tag) => tag.trim().toLowerCase()).filter(Boolean))].slice(0, 50))}/>;
}

interface MetadataRow { readonly key: string; readonly value: string }

function toRows(metadata: DocumentMetadata): readonly MetadataRow[] {
  const rows = Object.entries(metadata).map(([key, value]) => ({ key, value: value === null ? '' : String(value) }));
  return rows.length ? rows : [{ key: '', value: '' }];
}

function toMetadata(rows: readonly MetadataRow[]): DocumentMetadata {
  const metadata: Record<string, JsonPrimitive> = {};
  for (const row of rows) if (row.key.trim()) metadata[row.key.trim()] = row.value;
  return metadata;
}

export function MetadataEditor({ value, onChange }: { readonly value: DocumentMetadata; readonly onChange: (value: DocumentMetadata) => void }) {
  const rows = toRows(value);
  const update = (index: number, field: keyof MetadataRow, next: string) => onChange(toMetadata(rows.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: next } : row)));
  return <fieldset className="space-y-2"><legend className="text-sm font-medium">Metadata</legend><p className="text-xs text-muted-foreground">Add searchable business labels. Provider-owned metadata remains isolated in extension namespaces.</p>{rows.map((row, index) => <div key={`${index}:${row.key}`} className="grid grid-cols-[1fr_1fr_auto] gap-2"><Input aria-label={`Metadata key ${index + 1}`} value={row.key} placeholder="Property" onChange={(event) => update(index, 'key', event.target.value)}/><Input aria-label={`Metadata value ${index + 1}`} value={row.value} placeholder="Value" onChange={(event) => update(index, 'value', event.target.value)}/><Button aria-label={`Remove metadata row ${index + 1}`} size="icon" variant="ghost" type="button" onClick={() => onChange(toMetadata(rows.filter((_, rowIndex) => rowIndex !== index)))}><Trash2 className="h-4 w-4"/></Button></div>)}<Button type="button" size="sm" variant="outline" onClick={() => onChange({ ...value, '': '' })}><Plus className="mr-2 h-4 w-4"/>Add property</Button></fieldset>;
}
