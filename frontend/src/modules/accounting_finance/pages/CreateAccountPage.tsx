/* eslint-disable max-lines-per-function -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
/**
 * Create Account Page - Chart of Accounts
 */
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select";
import { accountingService, createIdempotencyKey } from "../services/accounting-service";
import type { AccountCreate } from "../contracts";

const MODULE_PATH = "/accounting-finance/accounts";
type FormErrors = Partial<Record<"code" | "name", string>>;

export const CreateAccountPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<AccountCreate>({
    code: "",
    name: "",
    account_type: "asset",
    normal_balance: "debit",
    is_active: true,
  });
  const [errors, setErrors] = useState<FormErrors>({});

  const createMutation = useMutation({
    mutationFn: (data: AccountCreate) =>
      accountingService.createAccount(data, createIdempotencyKey("account.create")),
    onSuccess: (account) => {
      void queryClient.invalidateQueries({ queryKey: ["accounting-accounts"] });
      toast.success("Account created successfully");
      navigate(`${MODULE_PATH}/${account.id}`);
    },
    onError: () => {
      toast.error("Failed to create account. Please try again.");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const nextErrors: FormErrors = {};
    if (!form.code.trim()) nextErrors.code = "Code is required";
    if (!form.name.trim()) nextErrors.name = "Name is required";
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }
    createMutation.mutate(form);
  };

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center gap-4">
        <Button variant="ghost" onClick={() => navigate(MODULE_PATH)}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>
        <h1 className="text-3xl font-bold text-foreground">Create Account</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Account Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div>
              <Input
                id="account-code"
                label="Code"
                value={form.code}
                onChange={(e) => {
                  setForm({ ...form, code: e.target.value });
                  if (errors.code) setErrors({ ...errors, code: undefined });
                }}
                placeholder="e.g. 1000"
                error={errors.code}
                required
              />
            </div>
            <div>
              <Input
                id="account-name"
                label="Name"
                value={form.name}
                onChange={(e) => {
                  setForm({ ...form, name: e.target.value });
                  if (errors.name) setErrors({ ...errors, name: undefined });
                }}
                placeholder="Account name"
                error={errors.name}
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Type</label>
              <Select
                value={form.account_type}
                onValueChange={(v) =>
                  setForm({ ...form, account_type: v as AccountCreate["account_type"] })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="asset">Asset</SelectItem>
                  <SelectItem value="liability">Liability</SelectItem>
                  <SelectItem value="equity">Equity</SelectItem>
                  <SelectItem value="revenue">Revenue</SelectItem>
                  <SelectItem value="expense">Expense</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Description</label>
              <Input
                value={form.description ?? ""}
                onChange={(e) => setForm({ ...form, description: e.target.value || undefined })}
                placeholder="Optional description"
              />
            </div>
            <div className="flex gap-2 pt-4">
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Creating..." : "Create Account"}
              </Button>
              <Button type="button" variant="outline" onClick={() => navigate(MODULE_PATH)}>
                Cancel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};
