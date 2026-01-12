import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Plus, Play, MoreVertical, Inbox } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { TableSkeleton, EmptyState, ErrorState } from "@/components/ui";
import { workflowService } from "../services/workflow-service";
import { toast } from "sonner";

export const WorkflowListPage = () => {
  const navigate = useNavigate();
  const {
    data: workflows,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["workflows"],
    queryFn: workflowService.workflows.list,
    retry: false, // Don't retry on auth errors
  });

  const handleStart = async (id: string, name: string) => {
    try {
      await workflowService.workflows.start(id);
      toast.success(`Started workflow: ${name}`);
    } catch (e) {
      toast.error("Failed to start workflow");
    }
  };

  const handlePublish = async (id: string) => {
    try {
      await workflowService.workflows.publish(id);
      toast.success("Workflow published");
      refetch();
    } catch (e) {
      toast.error("Failed to publish");
    }
  };

  if (isLoading)
    return (
      <div className="p-8">
        <TableSkeleton rows={3} columns={4} />
      </div>
    );

  if (error) {
    return (
      <div className="p-8">
        <ErrorState
          message={
            error instanceof Error
              ? error.message
              : "Failed to load workflows. Please check your connection and try again."
          }
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold">Workflows</h1>
          <p className="text-muted-foreground">
            Manage and monitor automation workflows
          </p>
        </div>
        <Button onClick={() => navigate("/workflow-automation/workflows/new")}>
          <Plus className="w-4 h-4 mr-2" />
          New Workflow
        </Button>
      </div>

      {!workflows?.length ? (
        <EmptyState
          icon={Inbox}
          title="No workflows defined"
          description="Create your first workflow to automate tasks."
          action={{
            label: "Create Workflow",
            onClick: () => navigate("/workflow-automation/workflows/new"),
          }}
        />
      ) : (
        <div className="grid gap-4">
          {workflows.map((wf) => (
            <Card key={wf.id} className="p-4 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-lg">{wf.name}</h3>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span
                    className={`px-2 py-0.5 rounded-full text-xs ${
                      wf.status === "published"
                        ? "bg-green-100 text-green-800"
                        : "bg-gray-100 text-gray-800"
                    }`}
                  >
                    {wf.status.toUpperCase()}
                  </span>
                  <span>•</span>
                  <span>{wf.steps.length} steps</span>
                  <span>•</span>
                  <span>{wf.trigger_type}</span>
                </div>
              </div>
              <div className="flex gap-2">
                {wf.status === "draft" && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handlePublish(wf.id)}
                  >
                    Publish
                  </Button>
                )}
                {wf.status === "published" && (
                  <Button size="sm" onClick={() => handleStart(wf.id, wf.name)}>
                    <Play className="w-4 h-4 mr-2" />
                    Run
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
