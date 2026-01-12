/**
 * Notification Center Page
 *
 * Displays all user notifications with filtering and actions.
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Bell, Check, CheckCheck, Filter } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { notificationService, type Notification } from '../services/notification-service';
import { cn } from '@/lib/utils';

export const NotificationCenterPage = () => {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<'all' | 'unread'>('all');

  const { data: notifications, isLoading, error, refetch } = useQuery({
    queryKey: ['notifications', filter],
    queryFn: () => notificationService.list(filter === 'unread'),
  });

  const markReadMutation = useMutation({
    mutationFn: (id: string) => notificationService.markRead(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notifications'] });
      void queryClient.invalidateQueries({ queryKey: ['notifications', 'unread-count'] });
    },
  });

  const markAllReadMutation = useMutation({
    mutationFn: notificationService.markAllRead,
    onSuccess: (count) => {
      toast.success(`Marked ${count} notifications as read`);
      void queryClient.invalidateQueries({ queryKey: ['notifications'] });
      void queryClient.invalidateQueries({ queryKey: ['notifications', 'unread-count'] });
    },
  });

  const getTypeColor = (type: Notification['type']): string => {
    const colors = {
      info: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200',
      success: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200',
      warning: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200',
      error: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200',
      workflow: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-200',
      approval: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-200',
      system: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-200',
    };
    return colors[type] || colors.info;
  };

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <TableSkeleton rows={5} columns={3} />
      </div>
    );
  }

  if (error) {
    return <ErrorState message="Failed to load notifications" onRetry={() => void refetch()} />;
  }

  const unreadCount = notifications?.filter((n) => !n.read).length || 0;

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Bell className="h-8 w-8" />
            Notifications
          </h1>
          <p className="text-muted-foreground mt-2">
            {unreadCount > 0 ? `${unreadCount} unread notification${unreadCount > 1 ? 's' : ''}` : 'All caught up!'}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => setFilter(filter === 'all' ? 'unread' : 'all')}
          >
            <Filter className="mr-2 h-4 w-4" />
            {filter === 'all' ? 'Show Unread' : 'Show All'}
          </Button>
          {unreadCount > 0 && (
            <Button
              variant="outline"
              onClick={() => markAllReadMutation.mutate()}
              disabled={markAllReadMutation.isPending}
            >
              <CheckCheck className="mr-2 h-4 w-4" />
              Mark All Read
            </Button>
          )}
        </div>
      </div>

      {!notifications || notifications.length === 0 ? (
        <EmptyState
          title="No notifications"
          description={filter === 'unread' ? "You're all caught up!" : "No notifications yet."}
        />
      ) : (
        <div className="space-y-2">
          {notifications.map((notification: Notification) => (
            <Card
              key={notification.id}
              className={cn(
                "p-4 hover:bg-muted/50 transition-colors",
                !notification.read && "border-l-4 border-l-primary bg-muted/30"
              )}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={cn("px-2 py-1 rounded text-xs font-medium", getTypeColor(notification.type))}>
                      {notification.type}
                    </span>
                    {!notification.read && (
                      <span className="h-2 w-2 rounded-full bg-primary" />
                    )}
                  </div>
                  <h3 className="font-semibold">{notification.title}</h3>
                  <p className="text-sm text-muted-foreground mt-1">{notification.message}</p>
                  <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                    <span>{formatDate(notification.created_at)}</span>
                    {notification.action_url && (
                      <a
                        href={notification.action_url}
                        className="text-primary hover:underline"
                      >
                        View Details
                      </a>
                    )}
                  </div>
                </div>
                {!notification.read && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => markReadMutation.mutate(notification.id)}
                    disabled={markReadMutation.isPending}
                    aria-label="Mark as read"
                  >
                    <Check className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
