/**
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Security Audit Log Page
 * 
 * Displays security audit logs for the current tenant.
 */
import { useQuery } from '@tanstack/react-query';
import { FileText, Search } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { securityService, type SecurityAuditLog } from '../services/security-service';
import { useState, useDeferredValue } from 'react';

export const AuditLogPage = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const deferredSearchQuery = useDeferredValue(searchQuery);
  const [actionFilter, setActionFilter] = useState<string>('');

  const { data: auditLogs, isLoading, error, refetch } = useQuery<SecurityAuditLog[]>({
    queryKey: ['security-audit-logs', actionFilter],
    queryFn: async (): Promise<SecurityAuditLog[]> => {
      const result = await securityService.auditLogs.list({
        action: actionFilter || undefined,
      });
      return Array.isArray(result) ? result : [];
    },
    refetchInterval: 30000, // Refetch every 30 seconds
  });

  // Type guard to ensure auditLogs is an array
  const safeAuditLogs: SecurityAuditLog[] = Array.isArray(auditLogs) ? auditLogs : [];

  const filteredLogs: SecurityAuditLog[] = safeAuditLogs.filter((log: SecurityAuditLog) => {
    if (deferredSearchQuery) {
      const query = deferredSearchQuery.toLowerCase();
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
      const action = String(log.action ?? '').toLowerCase();
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
      const resourceType = String(log.resource_type ?? '').toLowerCase();
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
      const actorIdStr = typeof log.actor_id === 'string' ? log.actor_id : String(log.actor_id ?? '');
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-call, @typescript-eslint/no-unsafe-member-access
      const actorId = String(actorIdStr).toLowerCase();
      return (
        action.includes(query) ||
        resourceType.includes(query) ||
        // eslint-disable-next-line @typescript-eslint/no-unsafe-call, @typescript-eslint/no-unsafe-member-access
        actorId.includes(query)
      );
    }
    return true;
  });

  // Get unique actions for filter
  const actions: string[] = Array.from(
    new Set(
      safeAuditLogs
        // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access, @typescript-eslint/no-unsafe-call
        .map((log) => String(log.action ?? ''))
        .filter((action): action is string => action.length > 0)
    )
  );

  const getSeverityColor = (decision?: string) => {
    if (decision === 'allow') return 'text-green-600';
    if (decision === 'deny') return 'text-red-600';
    return 'text-muted-foreground';
  };

  if (isLoading) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <TableSkeleton rows={5} columns={6} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <ErrorState
          message="Failed to load audit logs. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-foreground mb-2">Security Audit Log</h1>
        <p className="text-muted-foreground">View security events and access decisions</p>
      </div>

      {/* Filters */}
      <Card className="p-4 mb-6">
        <div className="flex items-center gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search audit logs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          <div className="w-48">
            <Select
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              options={[
                { value: '', label: 'All Actions' },
                ...actions.map((action: string) => ({ value: action, label: action })),
              ]}
            />
          </div>
        </div>
      </Card>

      {/* Audit Logs List */}
      {filteredLogs && filteredLogs.length > 0 ? (
        <div className="space-y-4">
          {filteredLogs.map((log) => {
            // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
            const logId = String(log.id ?? `log-${Math.random()}`);
            // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
            const logAction = log.action ?? 'Unknown';
            // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
            const logDecision = log.decision;
            // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
            const logActorId = log.actor_id;
            // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
            const logActorType = log.actor_type;
            // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
            const logResourceType = log.resource_type;
            // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
            const logResourceId = log.resource_id;
            // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
            const logTimestamp = log.timestamp;
            // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
            const logIpAddress = log.ip_address;
            // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
            const logReasonCodes = log.reason_codes;

            return (
              <Card key={logId} className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-4 flex-1">
                    <div className="p-2 bg-primary-main/10 dark:bg-primary-main/20 rounded-lg">
                      <FileText className="w-5 h-5 text-primary-main" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-semibold text-foreground">{String(logAction)}</span>
                        {logDecision && typeof logDecision === 'string' && (
                          <span className={`text-sm font-medium ${getSeverityColor(logDecision)}`}>
                            ({logDecision.toUpperCase()})
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-muted-foreground space-y-1">
                        <div>
                          <span className="font-medium">Actor:</span> {String(logActorId ?? '')} ({String(logActorType ?? 'unknown')})
                        </div>
                        {logResourceType && (
                          <div>
                            <span className="font-medium">Resource:</span> {String(logResourceType)}
                            {logResourceId && ` (${String(logResourceId)})`}
                          </div>
                        )}
                        {logTimestamp && (
                          <div>
                            <span className="font-medium">Time:</span>{' '}
                            {new Date(String(logTimestamp)).toLocaleString()}
                          </div>
                        )}
                        {logIpAddress && (
                          <div>
                            <span className="font-medium">IP:</span> {String(logIpAddress)}
                          </div>
                        )}
                        {(() => {
                          if (logReasonCodes && Array.isArray(logReasonCodes) && logReasonCodes.length > 0) {
                            return (
                              <div>
                                <span className="font-medium">Reason Codes:</span>{' '}
                                <span>{(logReasonCodes as string[]).join(', ')}</span>
                              </div>
                            );
                          }
                          return null;
                        })()}
                      </div>
                    </div>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      ) : (
        <EmptyState
          icon={FileText}
          title="No audit logs found"
          description="No audit logs match your search criteria."
        />
      )}
    </div>
  );
};

