import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Save, Trash, ArrowLeft } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/Select";
import { toast } from "sonner";
import { workflowService } from "../services/workflow-service";
import { WorkflowStep } from "../contracts";

export const WorkflowBuilder = () => {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [triggerType, setTriggerType] = useState("manual");
  const [steps, setSteps] = useState<Partial<WorkflowStep>[]>([]);
  const [isSaving, setIsSaving] = useState(false);

  const addStep = () => {
    setSteps([
      ...steps,
      {
        name: `Step ${steps.length + 1}`,
        step_type: "action",
        order: steps.length + 1,
        config: {},
      },
    ]);
  };

  const removeStep = (index: number) => {
    const newSteps = [...steps];
    newSteps.splice(index, 1);
    // Reorder
    newSteps.forEach((step, idx) => {
      step.order = idx + 1;
    });
    setSteps(newSteps);
  };

  const updateStep = (index: number, field: keyof WorkflowStep, value: any) => {
    const newSteps = [...steps];
    newSteps[index] = { ...newSteps[index], [field]: value };
    setSteps(newSteps);
  };

  const handleSave = async () => {
    if (!name) {
      toast.error("Please enter a workflow name");
      return;
    }
    if (steps.length === 0) {
      toast.error("Please add at least one step");
      return;
    }

    setIsSaving(true);
    try {
      await workflowService.workflows.create({
        name,
        description,
        trigger_type: triggerType as any,
        steps: steps as any,
        status: "draft",
      });
      toast.success("Workflow created successfully");
      navigate("/workflow-automation/workflows");
    } catch (error) {
      toast.error("Failed to create workflow");
      console.error(error);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            onClick={() => navigate("/workflow-automation/workflows")}
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
          <h1 className="text-3xl font-bold">Create Workflow</h1>
        </div>
        <Button onClick={handleSave} disabled={isSaving}>
          <Save className="w-4 h-4 mr-2" />
          {isSaving ? "Saving..." : "Save Workflow"}
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-8">
        <Card className="p-6 col-span-1 h-fit">
          <h3 className="text-lg font-semibold mb-4">Settings</h3>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium">Name</label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Purchase Approval"
              />
            </div>
            <div>
              <label className="text-sm font-medium">Description</label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional description"
              />
            </div>
            <div>
              <label className="text-sm font-medium">Trigger Type</label>
              <Select value={triggerType} onValueChange={setTriggerType}>
                <SelectTrigger>
                  <SelectValue placeholder="Select trigger type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual">Manual</SelectItem>
                  <SelectItem value="event">Event</SelectItem>
                  <SelectItem value="scheduled">Scheduled</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </Card>

        <div className="col-span-2 space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">Workflow Steps</h3>
            <Button variant="outline" size="sm" onClick={addStep}>
              <Plus className="w-4 h-4 mr-2" />
              Add Step
            </Button>
          </div>

          {steps.length === 0 && (
            <div className="text-center p-8 border-2 border-dashed rounded-lg text-muted-foreground">
              No steps added. Click "Add Step" to begin.
            </div>
          )}

          {steps.map((step, index) => (
            <Card key={index} className="p-4 relative">
              <div className="absolute top-4 right-4">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeStep(index)}
                  className="text-red-500 hover:text-red-700"
                >
                  <Trash className="w-4 h-4" />
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-medium uppercase text-muted-foreground">
                    Step Name
                  </label>
                  <Input
                    value={step.name}
                    onChange={(e) => updateStep(index, "name", e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-xs font-medium uppercase text-muted-foreground">
                    Type
                  </label>
                  <Select
                    value={step.step_type}
                    onValueChange={(value) =>
                      updateStep(index, "step_type", value)
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select step type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="action">Action</SelectItem>
                      <SelectItem value="approval">Approval</SelectItem>
                      { value: "notification", label: "Notification" },
                    ]}
                  />
                </div>
                {step.step_type === "approval" && (
                  <div className="col-span-2">
                    <label className="text-xs font-medium uppercase text-muted-foreground">
                      Assignee ID (User UUID)
                    </label>
                    <Input
                      value={(step.config?.assignee_id as string) || ""}
                      onChange={(e) =>
                        updateStep(index, "config", {
                          ...step.config,
                          assignee_id: e.target.value,
                        })
                      }
                      placeholder="Enter User UUID for Phase 8 testing"
                    />
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
};
