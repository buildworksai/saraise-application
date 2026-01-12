/**
 * Activity Timeline Component
 *
 * Displays activities in a timeline view.
 */
import { Clock, CheckCircle, Circle } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import type { Activity } from '../contracts';

interface ActivityTimelineProps {
  activities: Activity[];
}

export const ActivityTimeline = ({ activities }: ActivityTimelineProps) => {
  return (
    <div className="space-y-4">
      {activities.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-8">No activities yet</p>
      ) : (
        activities.map((activity) => (
          <Card key={activity.id} className="p-4">
            <div className="flex items-start gap-4">
              <div className="mt-1">
                {activity.completed ? (
                  <CheckCircle className="w-5 h-5 text-green-600" />
                ) : (
                  <Circle className="w-5 h-5 text-muted-foreground" />
                )}
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">{activity.subject}</p>
                    <p className="text-xs text-muted-foreground capitalize">{activity.activity_type}</p>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Clock className="w-4 h-4" />
                    {new Date(activity.created_at).toLocaleString()}
                  </div>
                </div>
                {activity.description && (
                  <p className="text-sm text-muted-foreground mt-2">{activity.description}</p>
                )}
              </div>
            </div>
          </Card>
        ))
      )}
    </div>
  );
};
