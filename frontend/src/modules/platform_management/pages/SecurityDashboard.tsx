/**
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Security Posture Dashboard
 * 
 * Shows security threats, vulnerability status, compliance status, access control metrics, and audit log summary.
 */
import { useQuery } from '@tanstack/react-query';
import { Loader2, Shield, AlertTriangle, CheckCircle2, Lock, FileText } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { platformService, type PlatformAlert } from '../services/platform-service';

export const SecurityDashboard = () => {
  const { data: securityAlerts, isLoading: alertsLoading } = useQuery<PlatformAlert[]>({
    queryKey: ['platform-alerts', 'security'],
    queryFn: () =>
      platformService.alerts.list().then((alerts) =>
        alerts.filter(
          (alert) =>
            alert.category === 'security' ||
            alert.severity === 'critical' ||
            alert.severity === 'high'
        )
      ),
    refetchInterval: 30000,
  });

  const isLoading = alertsLoading;

  if (isLoading) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <div className="flex items-center justify-center min-h-[400px]">
          <Loader2 className="w-8 h-8 animate-spin text-primary-main" />
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-foreground mb-2">Security Posture</h1>
        <p className="text-muted-foreground">Monitor security threats, vulnerabilities, and compliance status</p>
      </div>

      {/* Security Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Active Threats</p>
              <p className="text-3xl font-bold text-foreground">
                {securityAlerts?.filter(a => a.severity === 'critical' || a.severity === 'high').length ?? 0}
              </p>
            </div>
            <AlertTriangle className="w-8 h-8 text-red-600 dark:text-red-400" />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Vulnerabilities</p>
              <p className="text-3xl font-bold text-foreground">N/A</p>
              <p className="text-xs text-muted-foreground mt-1">Vulnerability scanning not configured</p>
            </div>
            <Shield className="w-8 h-8 text-green-600 dark:text-green-400" />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Compliance Status</p>
              <p className="text-3xl font-bold text-foreground">Not configured</p>
              <p className="text-xs text-muted-foreground mt-1">Compliance reporting not configured</p>
            </div>
            <CheckCircle2 className="w-8 h-8 text-green-600 dark:text-green-400" />
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Access Control</p>
              <p className="text-3xl font-bold text-foreground">N/A</p>
              <p className="text-xs text-muted-foreground mt-1">Policy Engine metrics not available</p>
            </div>
            <Lock className="w-8 h-8 text-green-600 dark:text-green-400" />
          </div>
        </Card>
      </div>

      {/* Security Alerts */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold mb-4">Security Alerts</h2>
        {securityAlerts && securityAlerts.length > 0 ? (
          <div className="space-y-3">
            {securityAlerts.map((alert, index) => (
              <Card key={alert.id ?? `security-alert-${index}`} className="p-4 border-l-4 border-l-red-500">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5" />
                  <div className="flex-1">
                    <div className="flex items-center justify-between mb-1">
                      <h4 className="font-semibold text-foreground">{alert.title ?? 'Security Alert'}</h4>
                      <span className="text-xs bg-red-100 dark:bg-red-900/40 px-2 py-1 rounded">
                        {alert.severity}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground">{alert.description ?? ''}</p>
                    {alert.source && (
                      <p className="text-xs text-muted-foreground mt-2">Source: {alert.source}</p>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        ) : (
          <Card className="p-6">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
              <div>
                <p className="font-medium">No security alerts</p>
                <p className="text-sm text-muted-foreground">All security systems are operating normally</p>
              </div>
            </div>
          </Card>
        )}
      </div>

      {/* Compliance Status */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold mb-4">Compliance</h2>
        <Card className="p-6">
          <div className="flex items-center gap-3 text-muted-foreground">
            <Shield className="w-5 h-5" />
            <p>Compliance status is not available until compliance reporting is configured (Security & Access Control + audit reporting).</p>
          </div>
        </Card>
      </div>

      {/* Audit Log Summary */}
      <div>
        <h2 className="text-2xl font-semibold mb-4">Recent Security Events</h2>
        <Card className="p-6">
          <div className="flex items-center gap-3 text-muted-foreground">
            <FileText className="w-5 h-5" />
            <p>Audit log summary will show recent security events, access attempts, and policy changes.</p>
          </div>
        </Card>
      </div>
    </div>
  );
};
