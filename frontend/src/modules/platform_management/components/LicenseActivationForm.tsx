/**
 * License Activation Form Component
 *
 * Allows admin to input license key and activate.
 */
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Key, Lock, CheckCircle2 } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ENDPOINTS, LicenseActivationRequest } from "../contracts";
import { apiClient } from "@/services/api-client";

export const LicenseActivationForm = () => {
  const queryClient = useQueryClient();
  const [licenseKey, setLicenseKey] = useState("");

  const activateMutation = useMutation({
    mutationFn: async (data: LicenseActivationRequest) => {
      return apiClient.post(ENDPOINTS.LICENSING.ACTIVATE, data);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["license-status"] });
      toast.success("License activated successfully");
      setLicenseKey("");
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to activate license");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!licenseKey.trim()) return;
    activateMutation.mutate({ license_key: licenseKey });
  };

  return (
    <Card className="p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-primary-main/10 rounded-lg">
          <Key className="w-5 h-5 text-primary-main" />
        </div>
        <div>
          <h2 className="text-lg font-semibold">Activate License</h2>
          <p className="text-sm text-muted-foreground">
            Enter your license key to activate full platform features.
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label
            htmlFor="licenseKey"
            className="block text-sm font-medium mb-2"
          >
            License Key
          </label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              id="licenseKey"
              type="password"
              value={licenseKey}
              onChange={(e) => setLicenseKey(e.target.value)}
              placeholder="sk_live_..."
              className="pl-10 font-mono"
              required
            />
          </div>
        </div>

        <Button
          type="submit"
          disabled={activateMutation.isPending || !licenseKey}
          className="w-full"
        >
          {activateMutation.isPending ? "Activating..." : "Activate License"}
        </Button>

        <div className="bg-muted/50 p-4 rounded-lg text-sm text-muted-foreground border">
          <div className="flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 mt-0.5 text-green-500" />
            <p>
              Your license key is securely encrypted. We never share your key
              with third parties without your permission.
            </p>
          </div>
        </div>
      </form>
    </Card>
  );
};
