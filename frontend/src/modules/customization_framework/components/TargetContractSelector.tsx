import { useQuery } from "@tanstack/react-query";
import type { ResourceContract } from "../contracts";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

interface TargetContractSelectorProps {
  readonly value: string;
  readonly onSelect: (contract: ResourceContract) => void;
}

function identity(contract: ResourceContract): string {
  return `${contract.module}/${contract.resource}@${contract.version}`;
}

export function TargetContractSelector({ value, onSelect }: TargetContractSelectorProps) {
  const query = useQuery({ queryKey: ["customization", "resource-contracts"], queryFn: () => service.listResourceContracts(true) });
  if (query.isPending) return <div className="h-10 animate-pulse rounded-md bg-muted" aria-label="Loading target contracts" />;
  if (query.error) return <p role="alert" className="text-sm text-destructive">Target contracts are unavailable. Retry before creating this customization.</p>;
  const contracts = query.data.data;
  return <label className="grid gap-1 text-sm font-medium sm:col-span-2">Registered target contract
    <select className="h-10 rounded-md border bg-background px-3" required value={value} onChange={(event) => { const selected = contracts.find(contract => identity(contract) === event.target.value); if (selected) onSelect(selected); }}>
      <option value="">Select a registered module resource</option>
      {contracts.map(contract => <option key={identity(contract)} value={identity(contract)} disabled={!contract.available}>{identity(contract)}{contract.available ? "" : " — capability unavailable"}</option>)}
    </select>
    {contracts.length === 0 ? <span className="text-xs text-muted-foreground">No module has registered a customization contract. Install or enable a compatible module.</span> : null}
  </label>;
}
