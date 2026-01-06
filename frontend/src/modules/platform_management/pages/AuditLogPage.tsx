/**
 * Platform Audit Log Page
 * 
 * Displays platform audit events (read-only).
 */
import { useState, useDeferredValue } from 'react';
import { useQuery } from '@tanstack/react-query';
import { platformService } from '../services/platform-service';
import { Search, FileText } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const AuditLogPage = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);

  const { data: events, isLoading, error, refetch } = useQuery({
    queryKey: ['platform-audit-events'],
    queryFn: platformService.auditEvents.list,
  });

  const filteredEvents = events?.filter((event) => {
    const action = event.action ?? '';
    const resourceType = event.resource_type ?? '';
    const actorType = event.actor_type ?? '';
    const matchesSearch = deferredSearchTerm === '' ||
      action.toLowerCase().includes(deferredSearchTerm.toLowerCase()) ||
      resourceType.toLowerCase().includes(deferredSearchTerm.toLowerCase()) ||
      actorType.toLowerCase().includes(deferredSearchTerm.toLowerCase());
    return matchesSearch;
  });

  if (isLoading) {
    return (
      <div className="p-8">
        <TableSkeleton rows={10} columns={6} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <ErrorState
          message="Failed to load audit events. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Platform Audit Log</h1>
        <p className="text-muted-foreground mt-1">
          View immutable audit trail of platform operations
        </p>
      </div>

      <Card className="p-6">
        <div className="mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search audit events by action, resource, or actor..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
        </div>

        {filteredEvents?.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No audit events found"
            description="Audit events will appear here as platform operations occur."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-3 font-semibold">Timestamp</th>
                  <th className="text-left p-3 font-semibold">Action</th>
                  <th className="text-left p-3 font-semibold">Actor</th>
                  <th className="text-left p-3 font-semibold">Resource</th>
                  <th className="text-left p-3 font-semibold">IP Address</th>
                  <th className="text-left p-3 font-semibold">Details</th>
                </tr>
              </thead>
              <tbody>
                {filteredEvents?.map((event) => (
                  <tr key={event.id} className="border-b hover:bg-muted/50">
                    <td className="p-3">
                      <span className="text-sm">
                        {event.timestamp ? new Date(event.timestamp).toLocaleString() : '-'}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className="text-sm font-mono">{event.action ?? '-'}</span>
                    </td>
                    <td className="p-3">
                      <div className="text-sm">
                        <span className="text-muted-foreground">{event.actor_type}:</span>
                        <span className="ml-1 font-mono">{event.actor_id}</span>
                      </div>
                    </td>
                    <td className="p-3">
                      <div className="text-sm">
                        <span className="text-muted-foreground">{event.resource_type}</span>
                        {event.resource_id && (
                          <span className="ml-1 font-mono text-muted-foreground">
                            ({event.resource_id})
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="p-3">
                      <span className="text-sm text-muted-foreground">
                        {event.ip_address ?? '-'}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className="text-sm text-muted-foreground">
                        {event.details && Object.keys(event.details).length > 0
                          ? JSON.stringify(event.details)
                          : '-'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};
