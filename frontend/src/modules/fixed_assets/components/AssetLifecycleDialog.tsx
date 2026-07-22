import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import type { AllowedCommand, CapitalizeRequest, DisposalRequest, FixedAsset, ImpairmentRequest, LifecyclePreview, TransferRequest } from '../contracts';
import { fixedAssetsService } from '../services/fixed-assets-service';
import { formatMoney, ProblemState, titleCase } from './FixedAssetsUI';

type LifecycleCommand = Extract<AllowedCommand, 'capitalize' | 'transfer' | 'impair' | 'dispose'>;
type CommandRequest = CapitalizeRequest | TransferRequest | ImpairmentRequest | DisposalRequest;

function textValue(values: FormData, key: string): string {
  const value = values.get(key);
  return typeof value === 'string' ? value : '';
}

function requestFor(command: LifecycleCommand, asset: FixedAsset, values: FormData): CommandRequest {
  const common = { effective_date: textValue(values, 'effective_date') };
  if (command === 'capitalize') return { ...common, depreciation_start_date: textValue(values, 'depreciation_start_date'), expected_version: asset.version };
  if (command === 'transfer') return { ...common, to_location: textValue(values, 'to_location'), to_cost_center: textValue(values, 'to_cost_center') };
  if (command === 'impair') return { ...common, recoverable_amount: textValue(values, 'recoverable_amount'), reason: textValue(values, 'reason') };
  return { ...common, proceeds: textValue(values, 'proceeds'), reason: textValue(values, 'reason') };
}

function preview(command: LifecycleCommand, id: string, request: CommandRequest): Promise<LifecyclePreview> {
  if (command === 'capitalize') return fixedAssetsService.previewCapitalize(id, request as CapitalizeRequest);
  if (command === 'transfer') return fixedAssetsService.previewTransfer(id, request as TransferRequest);
  if (command === 'impair') return fixedAssetsService.previewImpair(id, request as ImpairmentRequest);
  return fixedAssetsService.previewDispose(id, request as DisposalRequest);
}

function execute(command: LifecycleCommand, id: string, request: CommandRequest): Promise<FixedAsset> {
  const key = `${command}:${id}:${request.effective_date}`;
  if (command === 'capitalize') return fixedAssetsService.capitalize(id, request as CapitalizeRequest, key);
  if (command === 'transfer') return fixedAssetsService.transfer(id, request as TransferRequest, key);
  if (command === 'impair') return fixedAssetsService.impair(id, request as ImpairmentRequest, key);
  return fixedAssetsService.dispose(id, request as DisposalRequest, key);
}

// eslint-disable-next-line complexity
export function AssetLifecycleDialog({ asset, command, open, onOpenChange, onComplete }: { asset: FixedAsset; command: LifecycleCommand; open: boolean; onOpenChange: (open: boolean) => void; onComplete: (asset: FixedAsset) => void }) {
  const [request, setRequest] = useState<CommandRequest | null>(null); const [confirmation, setConfirmation] = useState('');
  const previewMutation = useMutation({ mutationFn: (value: CommandRequest) => preview(command, asset.id, value), onSuccess: (_, value) => setRequest(value) });
  const commandMutation = useMutation({ mutationFn: (value: CommandRequest) => execute(command, asset.id, value), onSuccess: (updated) => { onComplete(updated); onOpenChange(false); setRequest(null); setConfirmation(''); } });
  const reset = (value: boolean) => { onOpenChange(value); if (!value) { previewMutation.reset(); commandMutation.reset(); setRequest(null); setConfirmation(''); } };
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); previewMutation.mutate(requestFor(command, asset, new FormData(event.currentTarget))); };
  const result = previewMutation.data; const destructive = command === 'dispose'; const confirmed = !destructive || confirmation === asset.asset_code;
  return <Dialog open={open} onOpenChange={reset} title={`${titleCase(command)} asset`} description="Preview is calculated by the authoritative financial service and bound to this asset version." size="lg">{!result ? <form className="space-y-4" onSubmit={submit}><Input id="effective-date" name="effective_date" type="date" label="Effective date" required/>{command === 'capitalize' && <Input id="depreciation-start" name="depreciation_start_date" type="date" label="Depreciation start date" required/>}{command === 'transfer' && <><Input id="to-location" name="to_location" label="New location" defaultValue={asset.location}/><Input id="to-cost-center" name="to_cost_center" label="New cost center" defaultValue={asset.cost_center}/></>}{command === 'impair' && <Input id="recoverable-amount" name="recoverable_amount" label="Recoverable amount" inputMode="decimal" required/>}{command === 'dispose' && <Input id="proceeds" name="proceeds" label="Disposal proceeds" inputMode="decimal" required/>}{(command === 'impair' || command === 'dispose') && <Textarea id="reason" name="reason" label="Reason" required/>}{previewMutation.error && <ProblemState error={previewMutation.error}/>}<div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => reset(false)}>Cancel</Button><Button type="submit" disabled={previewMutation.isPending}>{previewMutation.isPending ? 'Calculating preview…' : 'Preview financial effect'}</Button></div></form> : <div className="space-y-5"><div className="grid gap-3 sm:grid-cols-2"><div className="rounded-md border p-4"><p className="text-xs text-muted-foreground">Opening book value</p><p className="text-lg font-semibold">{formatMoney(result.opening_net_book_value, result.currency)}</p></div><div className="rounded-md border p-4"><p className="text-xs text-muted-foreground">Closing book value</p><p className="text-lg font-semibold">{formatMoney(result.closing_net_book_value, result.currency)}</p></div></div><p className="text-sm"><strong>Schedule effect:</strong> {result.schedule_effect.description}</p>{result.warnings.map((warning) => <p key={warning.code} role="note" className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">{warning.message} <span className="font-mono text-xs">({warning.code})</span></p>)}{result.blockers.map((blocker) => <p key={blocker.code} role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{blocker.message} <span className="font-mono text-xs">({blocker.code})</span></p>)}{destructive && <Input id="typed-confirmation" label={`Type ${asset.asset_code} to confirm irreversible disposal`} value={confirmation} onChange={(event) => setConfirmation(event.target.value)}/>} {commandMutation.error && <ProblemState error={commandMutation.error}/>}<div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => { setRequest(null); previewMutation.reset(); }}>Change details</Button><Button variant={destructive ? 'danger' : 'primary'} disabled={!request || !confirmed || result.blockers.length > 0 || commandMutation.isPending} onClick={() => { if (request) commandMutation.mutate(request); }}>{commandMutation.isPending ? 'Applying…' : `Confirm ${command}`}</Button></div></div>}</Dialog>;
}
