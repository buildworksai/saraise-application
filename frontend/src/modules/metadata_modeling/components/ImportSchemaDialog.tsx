import { useRef, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import type { ExportDocument, ImportRequest } from "../contracts";

interface Props { open: boolean; onOpenChange: (open: boolean) => void; onImport: (request: ImportRequest) => Promise<void> }
function isExportDocument(value: unknown): value is ExportDocument { if (typeof value !== "object" || value === null || Array.isArray(value)) return false; const document = value as Record<string, unknown>; return typeof document.format_version === "string" && typeof document.checksum === "string" && typeof document.entity === "object" && document.entity !== null && typeof document.schema === "object" && document.schema !== null; }

export function ImportSchemaDialog({ open, onOpenChange, onImport }: Props) {
  const input = useRef<HTMLInputElement>(null); const [document, setDocument] = useState<ExportDocument | null>(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const read = async (file: File) => { try { const parsed: unknown = JSON.parse(await file.text()); if (!isExportDocument(parsed)) throw new Error("The document is missing format_version, entity, schema, or checksum."); setDocument(parsed); setError(""); } catch (reason) { setDocument(null); setError(reason instanceof Error ? reason.message : "Invalid JSON document."); } };
  const validateImport = async () => { if (!document) return; setBusy(true); try { await onImport({ document, mode: "validate_only" }); onOpenChange(false); } finally { setBusy(false); } };
  return <Dialog open={open} onOpenChange={onOpenChange} title="Import metadata model" description="Validate a versioned export before creating anything." size="lg"><div className="space-y-4"><input ref={input} type="file" accept="application/json,.json" aria-label="Schema JSON document" onChange={(event) => { const file = event.target.files?.[0]; if (file) void read(file); }} />{document && <p className="text-sm text-muted-foreground">Format {document.format_version}; checksum {document.checksum.slice(0, 12)}…</p>}{error && <p role="alert" className="text-sm text-destructive">{error}</p>}<div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button type="button" disabled={!document || busy} onClick={() => void validateImport()}>{busy ? "Validating…" : "Validate import"}</Button></div></div></Dialog>;
}
