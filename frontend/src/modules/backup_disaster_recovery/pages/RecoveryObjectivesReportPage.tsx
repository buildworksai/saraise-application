import { useEffect, useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity, Download } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import type { ObjectiveBucket, ObjectiveReportFilters } from '../contracts';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { useBackupDisasterRecoveryConfiguration } from '../hooks/useBackupDisasterRecoveryConfiguration';
import { BackgroundProgress, DomainEmptyState, FormField, MetricCard, ModuleErrorState, PageHeader, PageShell, PageSkeleton, ResponsiveTable, formatDateTime, inputClass } from '../components/ModuleUi';

export const RecoveryObjectivesReportPage = () => {
  const configuration = useBackupDisasterRecoveryConfiguration();
  const [from,setFrom] = useState('');
  const [to,setTo] = useState('');
  const [bucket,setBucket] = useState<ObjectiveBucket | ''>('');
  const [runbookId,setRunbookId] = useState('');
  const [validation,setValidation] = useState('');
  const [filters,setFilters] = useState<ObjectiveReportFilters | null>(null);
  useEffect(() => {
    if (!configuration.data || filters) return;
    const reportConfiguration = configuration.data.document.reports;
    const end = new Date();
    const start = new Date(end);
    start.setUTCDate(start.getUTCDate() - reportConfiguration.default_interval_days);
    const startDate = start.toISOString().slice(0, 10);
    const endDate = end.toISOString().slice(0, 10);
    setFrom(startDate);
    setTo(endDate);
    setBucket(reportConfiguration.default_bucket);
    setFilters({ from: new Date(`${startDate}T00:00:00`).toISOString(), to: new Date(`${endDate}T23:59:59`).toISOString(), bucket: reportConfiguration.default_bucket });
  }, [configuration.data, filters]);
  const query = useQuery({ queryKey: ['bdr','objectives',filters], queryFn: () => filters ? backupDisasterRecoveryService.getObjectiveReport(filters) : Promise.reject(new Error('Report configuration unavailable')), enabled: filters !== null });
  if (configuration.error) return <ModuleErrorState error={configuration.error} onRetry={() => { void configuration.refetch(); }} />;
  if (query.error) return <ModuleErrorState error={query.error} onRetry={() => { void query.refetch(); }} />;
  if (query.isLoading || configuration.isLoading || !filters) return <PageSkeleton cards={4} />;
  if (!configuration.data) return <PageSkeleton cards={4} />;
  const report = query.data;
  const applyFilters = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (!from || !to || !bucket || new Date(from) > new Date(to)) { setValidation('Choose a valid date range and configured bucket with From before To.'); return; } setValidation(''); setFilters({ runbook_id: runbookId.trim() || undefined, from: new Date(`${from}T00:00:00`).toISOString(), to: new Date(`${to}T23:59:59`).toISOString(), bucket }); };
  const download = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `disaster-recovery-objectives-${from}-${to}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };
  return <PageShell><BackgroundProgress active={query.isFetching} /><PageHeader title="Recovery objectives" description="RPO and RTO outcomes include failed restores and remain grouped by immutable runbook version." actions={<Button variant="outline" disabled={!report} onClick={download}><Download className="mr-2 h-4 w-4" />Download JSON</Button>} />
    <Card><CardContent className="pt-6"><form onSubmit={applyFilters} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5"><FormField id="from" label="From"><input id="from" type="date" className={inputClass} value={from} onChange={(event) => setFrom(event.target.value)} /></FormField><FormField id="to" label="To"><input id="to" type="date" className={inputClass} value={to} onChange={(event) => setTo(event.target.value)} /></FormField><FormField id="bucket" label="Bucket"><select id="bucket" className={inputClass} value={bucket} onChange={(event) => setBucket(event.target.value as ObjectiveBucket)}>{configuration.data.document.reports.allowed_buckets.map((value) => <option key={value} value={value}>{value}</option>)}</select></FormField><FormField id="runbook" label="Runbook ID"><input id="runbook" className={inputClass} value={runbookId} onChange={(event) => setRunbookId(event.target.value)} placeholder="All runbooks" /></FormField><div className="flex items-end"><Button type="submit" className="w-full">Apply filters</Button></div>{validation ? <p role="alert" className="text-sm text-destructive sm:col-span-2 lg:col-span-5">{validation}</p> : null}</form></CardContent></Card>
    {report ? <><section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"><MetricCard label="RPO compliance" value={`${report.rpo_compliance_percent.toFixed(1)}%`} hint="Across all completed and failed restores" /><MetricCard label="RTO compliance" value={`${report.rto_compliance_percent.toFixed(1)}%`} hint="Across all completed and failed restores" /><MetricCard label="Total restores" value={String(report.total_restores)} hint={`${formatDateTime(report.from)} to ${formatDateTime(report.to)}`} /><MetricCard label="Failed restores" value={String(report.failed_restores)} hint="Failures remain in compliance totals" state={report.failed_restores ? 'bad' : 'good'} /></section>
      {report.buckets.length ? <ResponsiveTable label="Objective report by period and runbook version" headers={['Period','Runbook version','Restores','Failures','RPO compliance','RTO compliance']}>{report.buckets.map((item) => <tr key={`${item.period_start}-${item.runbook_id}-${item.runbook_version}`}><td className="px-4 py-3">{formatDateTime(item.period_start)} – {formatDateTime(item.period_end)}</td><td className="px-4 py-3">{item.runbook_name} · v{item.runbook_version}</td><td className="px-4 py-3">{item.restore_count}</td><td className="px-4 py-3">{item.failed_restore_count}</td><td className="px-4 py-3">{item.rpo_compliance_percent.toFixed(1)}%</td><td className="px-4 py-3">{item.rto_compliance_percent.toFixed(1)}%</td></tr>)}</ResponsiveTable> : <DomainEmptyState icon={Activity} title="No objective measurements" description="Complete a restore or recovery exercise in this reporting period to generate RPO and RTO evidence." />}</> : null}
  </PageShell>;
};
