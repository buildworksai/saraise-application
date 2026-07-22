import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { ApiProblem, PageHeader, PageSkeleton } from '../components/ModuleShell';
import { deterministicKey } from '../components/utils';
import { PROCESS_MINING_ROUTES, type MiningAlgorithm } from '../contracts';
import { processMiningService } from '../services/process_mining-service';

export function CreateDiscoveryPage() {
  const navigate = useNavigate(); const [params] = useSearchParams();
  const [processName, setProcessName] = useState(params.get('process_name') ?? '');
  const configuration = useQuery({ queryKey: ['process-mining', 'configuration'], queryFn: processMiningService.getConfiguration });
  const [algorithm, setAlgorithm] = useState<MiningAlgorithm>('alpha_miner'); const [threshold, setThreshold] = useState('');
  useEffect(() => { if (configuration.data) { const config = configuration.data.document; setAlgorithm(config.default_discovery_algorithm); setThreshold(String(config.default_discovery_algorithm === 'heuristic_miner' ? config.heuristic_default_threshold : config.inductive_default_threshold)); } }, [configuration.data]);
  const preview = useQuery({ queryKey: ['process-mining', 'discovery-preview', processName], queryFn: () => processMiningService.listProcesses({ process_name: processName, page_size: 1 }), enabled: processName.trim().length > 1 });
  const mutation = useMutation({ mutationFn: () => processMiningService.createDiscovery({ process_name: processName.trim(), algorithm, parameters: algorithm === 'heuristic_miner' ? { dependency_threshold: Number(threshold) } : algorithm === 'inductive_miner' ? { noise_threshold: Number(threshold) } : {}, idempotency_key: deterministicKey('discovery', processName, algorithm, threshold, new Date().toISOString()) }), onSuccess: (job) => navigate(PROCESS_MINING_ROUTES.DISCOVERY(job.id)) });
  if (configuration.isLoading || !configuration.data) return <PageSkeleton/>;
  const config = configuration.data.document; const evidence = preview.data?.items[0]; const numericThreshold = Number(threshold);
  const eligible = Boolean(evidence && evidence.event_count >= config.discovery_min_events && evidence.case_count >= config.discovery_min_cases && numericThreshold >= config.algorithm_threshold_min && numericThreshold <= config.algorithm_threshold_max);
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Create discovery" description="Validate configured evidence and compute policy before reserving durable capacity."/>{mutation.error && <ApiProblem error={mutation.error} onRetry={() => mutation.reset()}/>}<Card className="mx-auto max-w-3xl p-6"><form className="space-y-5" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}><Input id="process" label="Process name" value={processName} onChange={(event) => setProcessName(event.target.value)} required/><label className="block text-sm font-medium" htmlFor="algorithm">Algorithm<select id="algorithm" className="mt-1 block w-full rounded-md border bg-background p-2" value={algorithm} onChange={(event) => { const next = event.target.value as MiningAlgorithm; setAlgorithm(next); setThreshold(String(next === 'heuristic_miner' ? config.heuristic_default_threshold : config.inductive_default_threshold)); }}><option value="alpha_miner">Alpha miner</option><option value="heuristic_miner">Heuristic miner</option><option value="inductive_miner">Inductive miner</option></select></label>{algorithm !== 'alpha_miner' && <Input id="threshold" label="Configured algorithm threshold" type="number" min={config.algorithm_threshold_min} max={config.algorithm_threshold_max} step={config.algorithm_threshold_step} value={threshold} onChange={(event) => setThreshold(event.target.value)}/>}<div className="rounded border p-4" aria-live="polite"><p className={eligible ? 'text-primary' : 'text-destructive'}>{evidence ? `${evidence.event_count} events · ${evidence.case_count} cases · ${eligible ? 'configured minimum met' : `requires ${config.discovery_min_events} events and ${config.discovery_min_cases} cases`}` : 'Enter an existing process name.'}</p></div><div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => navigate(PROCESS_MINING_ROUTES.DISCOVERIES)}>Cancel</Button><Button type="submit" disabled={!eligible || mutation.isPending}>Queue discovery</Button></div></form></Card></main>;
}
