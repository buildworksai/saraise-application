/* eslint-disable @typescript-eslint/no-misused-promises, max-lines-per-function -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
import { useEffect, useRef } from "react";
import { useForm } from "react-hook-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { REGIONAL_QUERY_KEYS, ROUTES, type RegionalResourceCreate } from "../contracts";
import { regionalService } from "../services/regional-service";
import { useRegionalDocumentTitle } from "../use-regional-document-title";

interface ResourceFormData {
  name: string;
  description: string;
}

export const CreateRegionalResourcePage = () => {
  useRegionalDocumentTitle("Create regional resource");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const idempotencyKey = useRef(crypto.randomUUID());
  const configuration = useQuery({
    queryKey: [...REGIONAL_QUERY_KEYS.configuration("active"), "active"],
    queryFn: regionalService.getActiveConfiguration,
  });
  const rules = configuration.data?.document.resource;
  const form = useForm<ResourceFormData>({
    defaultValues: { name: "", description: "" },
  });

  useEffect(() => {
    if (!rules || form.formState.isDirty) return;
    form.reset({
      name: rules.name_default,
      description: rules.description_default,
    });
  }, [form, rules]);

  const createMutation = useMutation({
    mutationFn: (data: RegionalResourceCreate) =>
      regionalService.createResource(data, idempotencyKey.current),
    onSuccess: (resource) => {
      void queryClient.invalidateQueries({ queryKey: REGIONAL_QUERY_KEYS.resources });
      toast.success("Resource created successfully");
      navigate(ROUTES.DETAIL(resource.id));
    },
    onError: () => toast.error("Failed to create resource. Please try again."),
  });

  if (configuration.isLoading) {
    return (
      <p role="status" className="p-8 text-muted-foreground">
        Loading configuration…
      </p>
    );
  }
  if (configuration.isError || !rules) {
    return (
      <ErrorState
        title="Configuration unavailable"
        message="The governed Regional defaults and safe limits could not be loaded. Creation is disabled."
        onRetry={() => void configuration.refetch()}
      />
    );
  }

  return (
    <main id="main-content" className="mx-auto max-w-4xl space-y-6 p-8">
      <div>
        <h1 className="text-3xl font-bold text-foreground">Create regional resource</h1>
        <p className="mt-2 text-muted-foreground">
          Fields are validated against the active tenant configuration.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Resource details</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={form.handleSubmit((data) =>
              createMutation.mutate({
                name: data.name.trim(),
                description: data.description || rules.description_default,
              })
            )}
          >
            <Input
              id="name"
              label="Name"
              required
              minLength={rules.name_min_length}
              maxLength={rules.name_max_length}
              title={`Enter ${rules.name_min_length}–${rules.name_max_length} characters.`}
              error={form.formState.errors.name?.message}
              {...form.register("name", {
                required: "Name is required",
                minLength: {
                  value: rules.name_min_length,
                  message: `Name must contain at least ${rules.name_min_length} characters`,
                },
                maxLength: {
                  value: rules.name_max_length,
                  message: `Name must contain at most ${rules.name_max_length} characters`,
                },
                validate: (value) =>
                  value.trim().length >= rules.name_min_length ||
                  `Name must contain at least ${rules.name_min_length} non-whitespace characters`,
              })}
            />
            <div>
              <label
                htmlFor="description"
                className="mb-1 block text-sm font-medium text-foreground"
              >
                Description
              </label>
              <Textarea
                id="description"
                rows={4}
                maxLength={rules.description_max_length}
                title={`Up to ${rules.description_max_length} characters.`}
                {...form.register("description", {
                  maxLength: {
                    value: rules.description_max_length,
                    message: `Description must contain at most ${rules.description_max_length} characters`,
                  },
                })}
              />
              {form.formState.errors.description ? (
                <p className="mt-1 text-sm text-destructive">
                  {form.formState.errors.description.message}
                </p>
              ) : null}
            </div>
            {createMutation.error ? (
              <p role="alert" className="text-sm text-destructive">
                {createMutation.error instanceof Error
                  ? createMutation.error.message
                  : "Resource creation failed."}
              </p>
            ) : null}
            <div className="flex gap-3 pt-2">
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Creating…" : "Create resource"}
              </Button>
              <Button type="button" variant="outline" onClick={() => navigate(ROUTES.ROOT)}>
                Cancel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </main>
  );
};
