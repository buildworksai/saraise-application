import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, X, Clock } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { TableSkeleton, EmptyState } from "@/components/ui";
import { workflowService } from "../services/workflow-service";
import { toast } from "sonner";

export const TaskInboxPage = () => {
  const {
    data: tasks,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["workflow-tasks"],
    queryFn: workflowService.tasks.list,
  });

  const handleAction = async (id: string, action: "complete" | "reject") => {
    try {
      if (action === "complete") {
        await workflowService.tasks.complete(id);
        toast.success("Task completed");
      } else {
        await workflowService.tasks.reject(id);
        toast.success("Task rejected");
      }
      refetch();
    } catch (e) {
      toast.error("Failed to update task");
    }
  };

  if (isLoading)
    return (
      <div className="p-8">
        <TableSkeleton rows={3} columns={4} />
      </div>
    );

  const pendingTasks = tasks?.filter((t) => t.status === "pending") || [];

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">My Tasks</h1>
        <p className="text-muted-foreground">Action items assigned to you</p>
      </div>

      {!pendingTasks.length ? (
        <EmptyState
          title="All caught up!"
          description="You have no pending tasks."
          icon={Clock}
        />
      ) : (
        <div className="grid gap-4">
          {pendingTasks.map((task) => (
            <Card key={task.id} className="p-6">
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-sm text-primary-main mb-1">
                    {task.workflow_name}
                  </div>
                  <h3 className="font-semibold text-lg mb-2">
                    {task.step_name}
                  </h3>
                  <div className="text-sm text-muted-foreground">
                    Created: {new Date(task.created_at).toLocaleString()}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    className="text-red-500 hover:text-red-700"
                    onClick={() => handleAction(task.id, "reject")}
                  >
                    <X className="w-4 h-4 mr-2" />
                    Reject
                  </Button>
                  <Button onClick={() => handleAction(task.id, "complete")}>
                    <Check className="w-4 h-4 mr-2" />
                    Approve / Complete
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
