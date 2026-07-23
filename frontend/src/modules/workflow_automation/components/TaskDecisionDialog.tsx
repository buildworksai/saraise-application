import { useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";
import { useWorkflowConfiguration } from "../hooks/use-workflow-configuration";

export function TaskDecisionDialog({ open, decision, taskName, pending, error, onOpenChange, onSubmit }: { open: boolean; decision: "complete" | "reject"; taskName: string; pending: boolean; error?: Error | null; onOpenChange: (open: boolean) => void; onSubmit: (reason: string) => void }) {
  const [reason, setReason] = useState(""); const rejecting = decision === "reject";
  const configuration = useWorkflowConfiguration();
  const maximum = configuration.data?.document.ui.reject_reason_max_length;
  if (!maximum) return null;
  return <Dialog open={open} onOpenChange={onOpenChange} title={rejecting ? `Reject ${taskName}` : `Complete ${taskName}`} description={rejecting ? "A reason is required and becomes part of the immutable decision evidence." : "Confirm that the requested human action is complete."}><div className="space-y-4">{rejecting ? <label htmlFor="decision-reason" className="block text-sm font-medium">Reason<Textarea id="decision-reason" autoFocus maxLength={maximum} required className="mt-1" value={reason} onChange={(event) => setReason(event.target.value)}/><span className="text-xs text-muted-foreground">{reason.length}/{maximum}</span></label> : null}{error ? <div role="alert" className="rounded border border-destructive/40 p-3 text-sm text-destructive">{error.message}</div> : null}<div className="flex justify-end gap-2"><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button variant={rejecting ? "danger" : "primary"} disabled={pending || rejecting && !reason.trim()} onClick={() => onSubmit(reason.trim())}>{pending ? "Recording decision…" : rejecting ? "Reject task" : "Complete task"}</Button></div></div></Dialog>;
}
