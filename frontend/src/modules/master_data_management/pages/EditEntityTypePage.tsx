import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { EntityTypeForm } from "../components/EntityTypeForm";
import { GovernedError, PageSkeleton, QUERY_KEYS } from "../components/MdmUI";
import { masterDataService } from "../services/master-data-service";
export function EditEntityTypePage() { const { id = "" } = useParams(); const query = useQuery({ queryKey: QUERY_KEYS.entityType(id), queryFn: () => masterDataService.entityTypes.get(id), enabled: Boolean(id) }); if (query.isLoading) return <PageSkeleton/>; if (query.error) return <GovernedError error={query.error} retry={() => void query.refetch()}/>; return query.data ? <EntityTypeForm existing={query.data.data}/> : <GovernedError error={new Error("Entity type not found.")}/>; }
