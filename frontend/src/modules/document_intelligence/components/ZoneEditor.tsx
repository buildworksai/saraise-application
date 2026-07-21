import { useRef, useState } from 'react';
import { Plus, Redo2, Trash2, Undo2, ZoomIn } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import type { ExpectedDataType, ExtractionTemplateZoneInput, ZoneType } from '../contracts';
import { validateZones } from './zone-utils';

const EMPTY_ZONE: ExtractionTemplateZoneInput = { zone_name: 'New field', extraction_key: 'new_field', zone_type: 'text', x: '0.1000', y: '0.1000', width: '0.3000', height: '0.1000', page_number: 1, expected_data_type: 'string', is_required: false };

function zoneType(value: string): ZoneType {
  if (value === 'table' || value === 'checkbox' || value === 'barcode') return value;
  return 'text';
}

function dataType(value: string): ExpectedDataType {
  if (value === 'integer' || value === 'decimal' || value === 'date' || value === 'boolean' || value === 'array') return value;
  return 'string';
}

function snap(value: number): string {
  return Math.max(0, Math.min(1, Math.round(value * 100) / 100)).toFixed(4);
}

function ZoneCanvas({ zones, selected, zoom, invalid, select, move }: { zones: readonly ExtractionTemplateZoneInput[]; selected: number; zoom: number; invalid: ReadonlySet<number>; select: (index: number) => void; move: (index: number, key: 'x' | 'y', amount: number) => void }) {
  return <div className="overflow-auto rounded-md border bg-muted/30 p-6"><div className="relative mx-auto aspect-[3/4] max-w-lg origin-top border bg-background shadow-sm" style={{ transform: `scale(${zoom / 100})`, marginBottom: `${Math.max(0, zoom - 100) * 3}px` }} aria-label="Template page canvas">{zones.map((zone, index) => <button type="button" key={`${zone.extraction_key}:${index}`} className={`absolute overflow-hidden border-2 p-1 text-left text-[10px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${invalid.has(index) ? 'border-destructive bg-destructive/10' : selected === index ? 'border-primary bg-primary/15' : 'border-amber-500 bg-amber-500/10'}`} style={{ left: `${Number(zone.x) * 100}%`, top: `${Number(zone.y) * 100}%`, width: `${Number(zone.width) * 100}%`, height: `${Number(zone.height) * 100}%` }} onClick={() => select(index)} onKeyDown={(event) => { if (event.key === 'ArrowLeft') move(index, 'x', -0.01); if (event.key === 'ArrowRight') move(index, 'x', 0.01); if (event.key === 'ArrowUp') move(index, 'y', -0.01); if (event.key === 'ArrowDown') move(index, 'y', 0.01); }}>{zone.zone_name}</button>)}</div></div>;
}

function ZoneFields({ zone, index, selected, update, remove, select }: { zone: ExtractionTemplateZoneInput; index: number; selected: boolean; update: (index: number, patch: Partial<ExtractionTemplateZoneInput>) => void; remove: (index: number) => void; select: (index: number) => void }) {
  const id = `template-zone-${index}`;
  return <fieldset className={`rounded-md border p-4 ${selected ? 'border-primary' : ''}`}><legend className="px-2 text-sm font-semibold">Zone {index + 1}</legend><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Input id={`${id}-name`} label="Name" value={zone.zone_name} onFocus={() => select(index)} onChange={(event) => update(index, { zone_name: event.target.value })} /><Input id={`${id}-key`} label="Output key" value={zone.extraction_key} onChange={(event) => update(index, { extraction_key: event.target.value })} />{(['x', 'y', 'width', 'height'] as const).map((key) => <Input id={`${id}-${key}`} key={key} label={key} type="number" min="0" max="1" step="0.01" value={zone[key]} onChange={(event) => update(index, { [key]: snap(Number(event.target.value)) })} />)}<Input id={`${id}-page`} label="Page" type="number" min="1" value={zone.page_number} onChange={(event) => update(index, { page_number: Number(event.target.value) })} /><label className="text-sm" htmlFor={`${id}-zone-type`}>Zone type<select id={`${id}-zone-type`} className="mt-1 block w-full rounded-md border bg-background p-2" value={zone.zone_type} onChange={(event) => update(index, { zone_type: zoneType(event.target.value) })}>{['text', 'table', 'checkbox', 'barcode'].map((value) => <option key={value}>{value}</option>)}</select></label><label className="text-sm" htmlFor={`${id}-data-type`}>Data type<select id={`${id}-data-type`} className="mt-1 block w-full rounded-md border bg-background p-2" value={zone.expected_data_type} onChange={(event) => update(index, { expected_data_type: dataType(event.target.value) })}>{['string', 'integer', 'decimal', 'date', 'boolean', 'array'].map((value) => <option key={value}>{value}</option>)}</select></label><label className="flex items-center gap-2 self-end p-2 text-sm"><input type="checkbox" checked={zone.is_required} onChange={(event) => update(index, { is_required: event.target.checked })} />Required</label><Button type="button" variant="danger" size="sm" onClick={() => remove(index)}><Trash2 className="mr-1 h-4 w-4" />Remove</Button></div></fieldset>;
}

export function ZoneEditor({ zones, onChange }: { zones: readonly ExtractionTemplateZoneInput[]; onChange: (zones: readonly ExtractionTemplateZoneInput[]) => void }) {
  const [selected, setSelected] = useState(0); const [zoom, setZoom] = useState(100);
  const [history, setHistory] = useState<readonly (readonly ExtractionTemplateZoneInput[])[]>([]); const [future, setFuture] = useState<readonly (readonly ExtractionTemplateZoneInput[])[]>([]);
  const latest = useRef(zones); latest.current = zones;
  const issues = validateZones(zones); const invalid = new Set(issues.map((issue) => issue.index));
  const commit = (next: readonly ExtractionTemplateZoneInput[]) => { setHistory((items) => [...items.slice(-19), latest.current]); setFuture([]); onChange(next); };
  const update = (index: number, patch: Partial<ExtractionTemplateZoneInput>) => commit(zones.map((zone, position) => position === index ? { ...zone, ...patch } : zone));
  const undo = () => { const previous = history.at(-1); if (!previous) return; setHistory((items) => items.slice(0, -1)); setFuture((items) => [latest.current, ...items]); onChange(previous); };
  const redo = () => { const next = future[0]; if (!next) return; setFuture((items) => items.slice(1)); setHistory((items) => [...items, latest.current]); onChange(next); };
  const move = (index: number, key: 'x' | 'y', amount: number) => update(index, { [key]: snap(Number(zones[index]?.[key] ?? 0) + amount) });
  const add = () => { commit([...zones, { ...EMPTY_ZONE, zone_name: `Field ${zones.length + 1}`, extraction_key: `field_${zones.length + 1}` }]); setSelected(zones.length); };
  return <section className="space-y-4" aria-labelledby="zone-editor-title"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 id="zone-editor-title" className="font-semibold">Normalized zone editor</h2><p className="text-xs text-muted-foreground">Select a zone and use arrow keys or numeric coordinates. Values snap to 1% guides.</p></div><div className="flex items-center gap-2"><Button type="button" variant="outline" size="icon" disabled={history.length === 0} aria-label="Undo zone change" onClick={undo}><Undo2 className="h-4 w-4" /></Button><Button type="button" variant="outline" size="icon" disabled={future.length === 0} aria-label="Redo zone change" onClick={redo}><Redo2 className="h-4 w-4" /></Button><label className="flex items-center gap-2 text-xs"><ZoomIn className="h-4 w-4" /><input type="range" min="70" max="150" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} aria-label="Editor zoom" />{zoom}%</label><Button type="button" size="sm" onClick={add}><Plus className="mr-1 h-4 w-4" />Zone</Button></div></div><ZoneCanvas zones={zones} selected={selected} zoom={zoom} invalid={invalid} select={setSelected} move={move} />{issues.length > 0 && <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive" role="alert">{issues.map((issue, index) => <p key={`${issue.index}:${index}`}>Zone {issue.index + 1}: {issue.message}</p>)}</div>}<div className="space-y-4"><h3 className="font-medium">Accessible numeric coordinates</h3>{zones.map((zone, index) => <ZoneFields key={`${zone.extraction_key}:${index}`} zone={zone} index={index} selected={selected === index} select={setSelected} update={update} remove={(position) => commit(zones.filter((_, candidate) => candidate !== position))} />)}</div></section>;
}
