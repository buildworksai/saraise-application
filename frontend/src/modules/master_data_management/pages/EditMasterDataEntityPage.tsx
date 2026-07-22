import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { EntityForm } from "../components/EntityForm";
import { GovernedError, PageSkeleton, QUERY_KEYS } from "../components/MdmUI";
import { masterDataService } from "../services/master-data-service";
export function EditMasterDataEntityPage() { const { id = "" } = useParams(); const query = useQuery({ queryKey: QUERY_KEYS.entity(id), queryFn: () => masterDataService.entities.get(id), enabled: Boolean(id) }); if (query.isLoading) return <PageSkeleton/>; if (query.error) return <GovernedError error={query.error} retry={() => void query.refetch()}/>; return query.data ? <EntityForm existing={query.data.data}/> : <GovernedError error={new Error("Entity not found.")}/>; }
