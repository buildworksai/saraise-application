/**
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Infrastructure Health Dashboard
 * 
 * Shows CPU usage, memory usage, disk I/O, network bandwidth, and database connections.
 */
import { useQuery } from '@tanstack/react-query';
import { Loader2, Cpu, HardDrive, Network, Database, TrendingUp } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { platformService, type PlatformHealth } from '../services/platform-service';

export const InfrastructureDashboard = () => {
  const { data: health, isLoading: healthLoading } = useQuery<PlatformHealth>({
    queryKey: ['platform-health'],
    queryFn: () => platformService.health.getCurrent(),
    refetchInterval: 30000,
  });

  const isLoading = healthLoading;

  if (isLoading) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <div className="flex items-center justify-center min-h-[400px]">
          <Loader2 className="w-8 h-8 animate-spin text-primary-main" />
        </div>
      </div>
    );
  }

  const checks = (health?.checks) ?? undefined;
  const dbCheck = checks?.database;
  const dbOk = dbCheck === 'ok';

  const metrics = health?.metrics as { cpu_percent?: number | null; memory_percent?: number | null; disk_io_mbps?: number | null; network_bandwidth_mbps?: number | null } | undefined;
  const cpuPercent = typeof metrics?.cpu_percent === 'number' ? metrics.cpu_percent : null;
  const memPercent = typeof metrics?.memory_percent === 'number' ? metrics.memory_percent : null;
  const diskIo = typeof metrics?.disk_io_mbps === 'number' ? metrics.disk_io_mbps : null;
  const netBw = typeof metrics?.network_bandwidth_mbps === 'number' ? metrics.network_bandwidth_mbps : null;

  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-foreground mb-2">Infrastructure Health</h1>
        <p className="text-muted-foreground">Monitor system resources and infrastructure performance</p>
      </div>

      {/* Resource Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">CPU Usage</p>
              <p className="text-3xl font-bold text-foreground">
                {cpuPercent !== null ? `${cpuPercent.toFixed(1)}%` : 'N/A'}
              </p>
            </div>
            <Cpu className="w-8 h-8 text-primary-main" />
          </div>
          <div className="w-full bg-muted rounded-full h-2">
            <div 
              className="bg-primary-main h-2 rounded-full transition-all"
              style={{ width: `${cpuPercent !== null ? Math.min(cpuPercent, 100) : 0}%` }}
            />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Memory Usage</p>
              <p className="text-3xl font-bold text-foreground">
                {memPercent !== null ? `${memPercent.toFixed(1)}%` : 'N/A'}
              </p>
            </div>
            <HardDrive className="w-8 h-8 text-primary-main" />
          </div>
          <div className="w-full bg-muted rounded-full h-2">
            <div 
              className="bg-primary-main h-2 rounded-full transition-all"
              style={{ width: `${memPercent !== null ? Math.min(memPercent, 100) : 0}%` }}
            />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Disk I/O</p>
              <p className="text-3xl font-bold text-foreground">
                {diskIo !== null ? `${diskIo.toFixed(1)} MB/s` : 'N/A'}
              </p>
            </div>
            <HardDrive className="w-8 h-8 text-primary-main" />
          </div>
          <div className="w-full bg-muted rounded-full h-2">
            <div 
              className="bg-primary-main h-2 rounded-full transition-all"
              style={{ width: `${diskIo !== null ? Math.min(diskIo / 2, 100) : 0}%` }}
            />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Network Bandwidth</p>
              <p className="text-3xl font-bold text-foreground">
                {netBw !== null ? `${netBw.toFixed(1)} Mbps` : 'N/A'}
              </p>
            </div>
            <Network className="w-8 h-8 text-primary-main" />
          </div>
          <div className="w-full bg-muted rounded-full h-2">
            <div 
              className="bg-primary-main h-2 rounded-full transition-all"
              style={{ width: `${netBw !== null ? Math.min(netBw / 2, 100) : 0}%` }}
            />
          </div>
        </Card>
      </div>

      {/* Database Connections */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold mb-4">Database Connections</h2>
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Database className="w-8 h-8 text-primary-main" />
              <div>
                <p className="text-sm font-medium text-muted-foreground">Database Status</p>
                <p className="text-2xl font-bold text-foreground">
                  {dbOk ? 'Healthy' : (typeof dbCheck === 'string' ? dbCheck : 'Unknown')}
                </p>
                {dbOk && (
                  <p className="text-xs text-muted-foreground mt-1">All systems operational</p>
                )}
              </div>
            </div>
            <div className="w-32 bg-muted rounded-full h-2">
              <div 
                className={`h-2 rounded-full ${dbOk ? 'bg-green-600' : 'bg-red-600'}`}
                style={{ width: dbOk ? '100%' : '0%' }}
              />
            </div>
          </div>
        </Card>
      </div>

      {/* Resource Trends */}
      <div>
        <h2 className="text-2xl font-semibold mb-4">Resource Trends</h2>
        <Card className="p-6">
          <div className="flex items-center gap-3 text-muted-foreground">
            <TrendingUp className="w-5 h-5" />
            <p>Historical resource usage charts will be displayed here. Charting library integration coming soon.</p>
          </div>
        </Card>
      </div>
    </div>
  );
};

