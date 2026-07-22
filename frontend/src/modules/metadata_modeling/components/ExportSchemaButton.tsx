import { useState } from "react";
import { Download } from "lucide-react";
import { Button, type ButtonProps } from "@/components/ui/Button";
import { metadataModelingService } from "../services/metadata-modeling-service";
export function ExportSchemaButton({ definitionId, code, ...buttonProps }: { definitionId: string; code: string } & ButtonProps) {
  const [busy, setBusy] = useState(false);
  const performExport = async () => { setBusy(true); try { const document = await metadataModelingService.exportDefinition(definitionId); const url = URL.createObjectURL(new Blob([JSON.stringify(document, null, 2)], { type: "application/json" })); const anchor = window.document.createElement("a"); anchor.href = url; anchor.download = `${code}.metadata-schema.json`; anchor.click(); URL.revokeObjectURL(url); } finally { setBusy(false); } };
  return <Button type="button" variant="outline" {...buttonProps} disabled={busy || buttonProps.disabled} onClick={(event) => { buttonProps.onClick?.(event); if (!event.defaultPrevented) void performExport(); }}><Download className="mr-2 h-4 w-4" />{busy ? "Exporting…" : "Export"}</Button>;
}
