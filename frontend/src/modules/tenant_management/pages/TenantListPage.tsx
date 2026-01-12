/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * Tenant List Page
 *
 * Lists all tenants with filtering, search, and management actions.
 */
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Plus, Search, Building2 } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { TableSkeleton, EmptyState, ErrorState } from "@/components/ui";
import { tenantService, type Tenant } from "../services/tenant-service";
import { TenantStatusBadge, type TenantStatus } from "../components";
import { useState, useDeferredValue } from "react";

export const TenantListPage = () => {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState("");
  const deferredSearchQuery = useDeferredValue(searchQuery);
  const [statusFilter, setStatusFilter] = useState<string>("");

  const {
    data: tenants,
    isLoading,
    error,
    refetch,
  } = useQuery<Tenant[]>({
    queryKey: ["tenants", statusFilter, deferredSearchQuery],
    queryFn: () =>
      tenantService.tenants.list({
        status: statusFilter || undefined,
        search: deferredSearchQuery || undefined,
      }),
    refetchInterval: 60000, // Refetch every minute
  });

  if (isLoading) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <TableSkeleton rows={5} columns={6} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 max-w-7xl mx-auto">
        <ErrorState
          message="Failed to load tenants. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold text-foreground mb-2">
            Tenant Management
          </h1>
          <p className="text-muted-foreground">
            Manage tenant organizations, subscriptions, and modules
          </p>
        </div>
        {/* Create action removed: Tenant creation must happen via Control Plane */}
      </div>

      {/* Filters */}
      <Card className="p-4 mb-6">
        <div className="flex items-center gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search tenants by name, slug, or email..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          <div className="w-48">
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              options={[
                { value: "", label: "All Statuses" },
                { value: "trial", label: "Trial" },
                { value: "active", label: "Active" },
                { value: "suspended", label: "Suspended" },
                { value: "cancelled", label: "Cancelled" },
                { value: "archived", label: "Archived" },
              ]}
            />
          </div>
        </div>
      </Card>

      {/* Tenant List */}
      {tenants && tenants.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {tenants.map((tenant) => (
            <Card
              key={tenant.id}
              className="p-6 hover:shadow-lg transition-all cursor-pointer"
              onClick={() => navigate(`/tenant-management/${tenant.id}`)}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-primary-main/10 dark:bg-primary-main/20 rounded-lg">
                    <Building2 className="w-5 h-5 text-primary-main" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-lg text-foreground">
                      {tenant.name}
                    </h3>
                    <p className="text-sm text-muted-foreground">
                      {tenant.slug}
                    </p>
                  </div>
                </div>
                <TenantStatusBadge status={tenant.status! as TenantStatus} />
              </div>

              <div className="space-y-2 text-sm">
                {tenant.primary_contact_email && (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <span className="font-medium">Contact:</span>
                    <span>{tenant.primary_contact_email}</span>
                  </div>
                )}
                {tenant.industry && (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <span className="font-medium">Industry:</span>
                    <span>{tenant.industry}</span>
                  </div>
                )}
                {tenant.company_size && (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <span className="font-medium">Size:</span>
                    <span>{tenant.company_size}</span>
                  </div>
                )}
                {tenant.created_at && (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <span className="font-medium">Created:</span>
                    <span>
                      {new Date(tenant.created_at).toLocaleDateString()}
                    </span>
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={Building2}
          title={
            searchQuery || statusFilter ? "No tenants found" : "No tenants yet"
          }
          description={
            searchQuery || statusFilter
              ? "Try adjusting your filters to find tenants."
              : "No tenants found. Tenants must be created via the Control Plane."
          }
        />
      )}
    </div>
  );
};
