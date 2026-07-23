import { useQuery } from '@tanstack/react-query';
import { ResourceList, useListFilters } from '../components/SalesUi';
import { SALES_PATHS, type CustomerFilters } from '../contracts';
import { salesQueryKeys, salesService } from '../services/sales-service';

export function CustomerListPage() {
  const filters = useListFilters() as CustomerFilters;
  const result = useQuery({ queryKey: salesQueryKeys.customers(filters), queryFn: () => salesService.listCustomers(filters) });
  return <ResourceList title="Customers" description="Tenant-safe customer profiles used throughout quotations, orders, and deliveries." createLabel="Create customer" createPath={`${SALES_PATHS.CUSTOMERS}/new`} detailPath={(id) => `${SALES_PATHS.CUSTOMERS}/${encodeURIComponent(id)}`} queryResult={result} emptyTitle="No customers yet" searchPlaceholder="Search code or name" orderingOptions={[{value:'customer_code',label:'Code A–Z'},{value:'customer_name',label:'Name A–Z'},{value:'-created_at',label:'Newest first'}]} filterOptions={[{key:'is_active',label:'Status',options:[{value:'true',label:'Active'},{value:'false',label:'Archived'}]}]} columns={[{key:'code',label:'Code',render:(row)=>row.customer_code},{key:'name',label:'Customer',render:(row)=>row.customer_name},{key:'currency',label:'Currency',render:(row)=>row.currency},{key:'status',label:'Status',render:(row)=>row.is_active?'Active':'Archived'}]} />;
}
