/**
 * Tenant Create Page
 * 
 * Form for creating a new tenant.
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft, Save } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { tenantService, type TenantCreate } from '../services/tenant-service';

export const TenantCreatePage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState<Partial<TenantCreate>>({
    name: '',
    slug: '',
    subdomain: '',
    status: 'trial',
  });

  const createMutation = useMutation({
    mutationFn: (data: TenantCreate) => tenantService.tenants.create(data),
    onSuccess: (tenant) => {
      void queryClient.invalidateQueries({ queryKey: ['tenants'] });
      toast.success('Tenant created successfully');
      navigate(`/tenant-management/${tenant.id}`);
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to create tenant. Please try again.';
      toast.error(message);
    },
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!formData.name || !formData.slug || (!formData.subdomain && !formData.custom_domain)) {
      toast.error('Please fill in all required fields');
      return;
    }

    await createMutation.mutateAsync(formData as TenantCreate);
  };

  const handleChange = (field: keyof TenantCreate, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    
    // Auto-generate slug from name
    if (field === 'name' && !formData.slug) {
      const slug = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
      setFormData((prev) => ({ ...prev, slug }));
    }
    
    // Auto-generate subdomain from slug
    if (field === 'slug' && !formData.subdomain && !formData.custom_domain) {
      setFormData((prev) => ({ ...prev, subdomain: value }));
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <Button
        variant="ghost"
        onClick={() => {
          navigate('/tenant-management');
        }}
        className="mb-6"
      >
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to Tenants
      </Button>

      <Card className="p-6">
        <h1 className="text-3xl font-bold mb-6">Create New Tenant</h1>

        <form
          onSubmit={(event) => {
            void handleSubmit(event);
          }}
          className="space-y-6"
        >
          {/* Basic Information */}
          <div className="space-y-4">
            <h2 className="text-xl font-semibold">Basic Information</h2>
            
            <div>
              <label className="block text-sm font-medium mb-2">
                Name <span className="text-red-500">*</span>
              </label>
              <Input
                type="text"
                value={formData.name ?? ''}
                onChange={(e) => handleChange('name', e.target.value)}
                placeholder="Acme Corporation"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">
                Slug <span className="text-red-500">*</span>
              </label>
              <Input
                type="text"
                value={formData.slug ?? ''}
                onChange={(e) => handleChange('slug', e.target.value)}
                placeholder="acme-corporation"
                required
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Subdomain
                </label>
                <Input
                  type="text"
                  value={formData.subdomain ?? ''}
                  onChange={(e) => handleChange('subdomain', e.target.value)}
                  placeholder="acme"
                  disabled={!!formData.custom_domain}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Either subdomain or custom domain is required
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Custom Domain
                </label>
                <Input
                  type="text"
                  value={formData.custom_domain ?? ''}
                  onChange={(e) => handleChange('custom_domain', e.target.value)}
                  placeholder="acme.com"
                  disabled={!!formData.subdomain}
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Status</label>
              <Select
                value={formData.status ?? 'trial'}
                onChange={(e) => handleChange('status', e.target.value)}
                options={[
                  { value: 'trial', label: 'Trial' },
                  { value: 'active', label: 'Active' },
                  { value: 'suspended', label: 'Suspended' },
                  { value: 'cancelled', label: 'Cancelled' },
                  { value: 'archived', label: 'Archived' },
                ]}
              />
            </div>
          </div>

          {/* Contact Information */}
          <div className="space-y-4">
            <h2 className="text-xl font-semibold">Contact Information</h2>
            
            <div>
              <label className="block text-sm font-medium mb-2">
                Primary Contact Name
              </label>
              <Input
                type="text"
                value={formData.primary_contact_name ?? ''}
                onChange={(e) => handleChange('primary_contact_name', e.target.value)}
                placeholder="John Doe"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">
                Primary Contact Email
              </label>
              <Input
                type="email"
                value={formData.primary_contact_email ?? ''}
                onChange={(e) => handleChange('primary_contact_email', e.target.value)}
                placeholder="john@acme.com"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">
                Primary Contact Phone
              </label>
              <Input
                type="tel"
                value={formData.primary_contact_phone ?? ''}
                onChange={(e) => handleChange('primary_contact_phone', e.target.value)}
                placeholder="+1 (555) 123-4567"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Billing Email
                </label>
                <Input
                  type="email"
                  value={formData.billing_email ?? ''}
                  onChange={(e) => handleChange('billing_email', e.target.value)}
                  placeholder="billing@acme.com"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Technical Email
                </label>
                <Input
                  type="email"
                  value={formData.technical_email ?? ''}
                  onChange={(e) => handleChange('technical_email', e.target.value)}
                  placeholder="tech@acme.com"
                />
              </div>
            </div>
          </div>

          {/* Company Information */}
          <div className="space-y-4">
            <h2 className="text-xl font-semibold">Company Information</h2>
            
            <div>
              <label className="block text-sm font-medium mb-2">Industry</label>
              <Input
                type="text"
                value={formData.industry ?? ''}
                onChange={(e) => handleChange('industry', e.target.value)}
                placeholder="Technology"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Company Size</label>
              <Select
                value={formData.company_size ?? ''}
                onChange={(e) => handleChange('company_size', e.target.value)}
                options={[
                  { value: '', label: 'Select size' },
                  { value: '1-10', label: '1-10 employees' },
                  { value: '11-50', label: '11-50 employees' },
                  { value: '51-200', label: '51-200 employees' },
                  { value: '201-500', label: '201-500 employees' },
                  { value: '500+', label: '500+ employees' },
                ]}
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Website URL</label>
              <Input
                type="url"
                value={formData.website_url ?? ''}
                onChange={(e) => handleChange('website_url', e.target.value)}
                placeholder="https://acme.com"
              />
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-4 pt-4 border-t">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                navigate('/tenant-management');
              }}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={createMutation.isPending}
            >
              <Save className="w-4 h-4 mr-2" />
              {createMutation.isPending ? 'Creating...' : 'Create Tenant'}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
};
