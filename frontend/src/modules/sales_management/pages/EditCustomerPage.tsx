import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { CustomerForm } from '../components/CustomerForm';
import { GovernedError, SalesPage } from '../components/SalesUi';
import { salesQueryKeys, salesService } from '../services/sales-service';
export function EditCustomerPage(){const {id}=useParams();const query=useQuery({queryKey:salesQueryKeys.customer(id??''),queryFn:()=>salesService.getCustomer(id??''),enabled:Boolean(id)});if(query.isLoading)return <SalesPage title="Edit customer" description="Loading customer…"><div className="h-64 animate-pulse rounded-lg bg-muted"/></SalesPage>;if(query.error||!query.data)return <SalesPage title="Edit customer" description="Customer could not be loaded."><GovernedError error={query.error} onRetry={()=>void query.refetch()}/></SalesPage>;return <CustomerForm customer={query.data}/>;}
