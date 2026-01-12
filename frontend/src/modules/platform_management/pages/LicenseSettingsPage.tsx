/**
 * License Settings Page
 *
 * Displays current license status and activation form.
 */
import { useQuery } from "@tanstack/react-query";
import { Shield, Check, X, AlertTriangle } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { LicenseActivationForm } from "../components/LicenseActivationForm";
import { ENDPOINTS, LicenseInfo } from "../contracts";
import { apiClient } from "@/services/api-client";

export const LicenseSettingsPage = () => {
  const { data: license, isLoading } = useQuery<LicenseInfo>({
    queryKey: ["license-status"],
    queryFn: () => apiClient.get(ENDPOINTS.LICENSING.STATUS),
  });

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">License Management</h1>
        <p className="text-muted-foreground">
          Manage your platform license, view limits, and check compliance
          status.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Main Status Panel */}
        <div className="lg:col-span-2 space-y-6">
          <Card className="p-6">
            <h2 className="text-xl font-semibold mb-6 flex items-center gap-2">
              <Shield className="w-5 h-5 text-primary-main" />
              License Status
            </h2>

            {isLoading ? (
              <div className="animate-pulse space-y-4">
                <div className="h-8 bg-muted rounded w-1/3"></div>
                <div className="h-4 bg-muted rounded w-1/2"></div>
              </div>
            ) : license ? (
              <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="p-4 bg-muted/30 rounded-lg border">
                    <p className="text-sm text-muted-foreground mb-1">
                      Current Tier
                    </p>
                    <p className="text-lg font-semibold capitalize">
                      {license.tier}
                    </p>
                  </div>
                  <div className="p-4 bg-muted/30 rounded-lg border">
                    <p className="text-sm text-muted-foreground mb-1">Status</p>
                    <div className="flex items-center gap-2">
                      <span
                        className={`w-2 h-2 rounded-full ${
                          license.is_valid ? "bg-green-500" : "bg-red-500"
                        }`}
                      />
                      <p className="text-lg font-semibold capitalize">
                        {license.status}
                      </p>
                    </div>
                  </div>
                  <div className="p-4 bg-muted/30 rounded-lg border">
                    <p className="text-sm text-muted-foreground mb-1">
                      Days Remaining
                    </p>
                    <p
                      className={`text-lg font-semibold ${
                        license.days_remaining < 7 ? "text-red-500" : ""
                      }`}
                    >
                      {license.days_remaining} Days
                    </p>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-medium text-muted-foreground mb-4">
                    Module Entitlements
                  </h3>
                  <div className="space-y-2">
                    {license.features.map((feature) => (
                      <div
                        key={feature.module}
                        className="flex items-center justify-between p-3 bg-card border rounded-md"
                      >
                        <span className="font-medium">{feature.module}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-muted-foreground uppercase">
                            {feature.tier_required}
                          </span>
                          {feature.licensed ? (
                            <Check className="w-4 h-4 text-green-500" />
                          ) : (
                            <X className="w-4 h-4 text-red-500" />
                          )}
                        </div>
                      </div>
                    ))}
                    {license.features.length === 0 && (
                      <p className="text-sm text-muted-foreground italic">
                        No specific module entitlements found.
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-red-500">
                <AlertTriangle className="w-5 h-5" />
                <p>Failed to load license information.</p>
              </div>
            )}
          </Card>
        </div>

        {/* Sidebar / Activation */}
        <div className="space-y-6">
          <LicenseActivationForm />

          <Card className="p-6 bg-blue-50/50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-900">
            <h3 className="font-semibold mb-2 text-blue-800 dark:text-blue-300">
              Need Help?
            </h3>
            <p className="text-sm text-blue-600 dark:text-blue-400 mb-4">
              Contact our support team if you have issues with your license
              activation or need to upgrade your tier.
            </p>
            <a
              href="mailto:support@saraise.com"
              className="text-sm font-medium text-blue-700 hover:underline"
            >
              Contact Support &rarr;
            </a>
          </Card>
        </div>
      </div>
    </div>
  );
};
