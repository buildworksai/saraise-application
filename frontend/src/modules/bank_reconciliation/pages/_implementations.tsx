/* eslint-disable max-lines-per-function -- audit pages keep each governed workflow visible end-to-end. */
import { useState, type ChangeEvent, type DragEvent, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  Archive,
  ArrowLeft,
  CheckCircle2,
  Download,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { ApiError } from "@/services/api-client";
import {
  QUERY_KEYS,
  ROUTES,
  type AccountType,
  type BankAccountCreate,
  type BankAccountFilters,
  type BankAccountUpdate,
  type ImportFilters,
  type ManualStatementCreate,
  type ManualTransactionInput,
  type MatchingRuleCreate,
  type MatchingRuleUpdate,
  type ParserFormat,
  type ReconciliationCreate,
  type ReconciliationFilters,
  type ReconciliationStatus,
  type RuleFilters,
  type RuleType,
  type StatementFilters,
  type TransactionFilters,
} from "../contracts";
import { bankReconciliationService as service } from "../services/bank-reconciliation-service";
import { fixedAdd } from "../math";
import {
  DetailGrid,
  EmptyPanel,
  ErrorPage,
  Field,
  FormCard,
  LoadingPage,
  Money,
  Page,
  Pager,
  StatusPill,
  TableShell,
  Td,
  Th,
} from "./_shared";

const idempotencyKey = () => globalThis.crypto.randomUUID();
const required = (value: string) => (value.trim() ? undefined : "This field is required.");
const getId = (value: string | undefined) => value ?? "";
const optionalValue = <T extends string>(value: T): T | undefined =>
  value === "" ? undefined : value;

export function BankAccountListPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [filters, setFilters] = useState<BankAccountFilters>({ page: 1, page_size: 25 });
  const query = useQuery({
    queryKey: QUERY_KEYS.accounts.list(filters),
    queryFn: () => service.listBankAccounts(filters),
  });
  const archive = useMutation({
    mutationFn: service.archiveBankAccount,
    onSuccess: () => {
      toast.success("Account archived. Financial history remains available.");
      void client.invalidateQueries({ queryKey: QUERY_KEYS.accounts.all });
    },
    onError: (error: Error) => toast.error(error.message),
  });
  if (query.isLoading) return <LoadingPage title="Bank accounts" />;
  if (query.error)
    return (
      <ErrorPage title="Bank accounts" error={query.error} retry={() => void query.refetch()} />
    );
  const result = query.data;
  return (
    <Page
      title="Bank accounts"
      description="Manage reconciliation accounts without exposing sensitive identifiers."
      actions={
        <Button onClick={() => navigate(ROUTES.ACCOUNT_CREATE)}>
          <Plus className="mr-2 h-4 w-4" />
          New account
        </Button>
      }
    >
      <Card>
        <CardContent className="grid gap-3 pt-6 md:grid-cols-4">
          <label className="relative md:col-span-2">
            <span className="sr-only">Search accounts</span>
            <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Search bank, account, or last four"
              value={filters.search ?? ""}
              onChange={(event) => setFilters({ ...filters, search: event.target.value, page: 1 })}
            />
          </label>
          <select
            aria-label="Account type"
            className="h-10 rounded-md border bg-background px-3"
            value={filters.account_type ?? ""}
            onChange={(event) =>
              setFilters({
                ...filters,
                account_type: optionalValue(event.target.value as AccountType),
                page: 1,
              })
            }
          >
            <option value="">All account types</option>
            {["checking", "savings", "credit", "cash", "other"].map((type) => (
              <option key={type}>{type}</option>
            ))}
          </select>
          <select
            aria-label="Account status"
            className="h-10 rounded-md border bg-background px-3"
            value={filters.is_active === undefined ? "" : String(filters.is_active)}
            onChange={(event) =>
              setFilters({
                ...filters,
                is_active: event.target.value === "" ? undefined : event.target.value === "true",
                page: 1,
              })
            }
          >
            <option value="">Any status</option>
            <option value="true">Active</option>
            <option value="false">Archived</option>
          </select>
        </CardContent>
      </Card>
      {!result?.items.length ? (
        <EmptyPanel
          title="No bank accounts found"
          description="Adjust the filters or add the first account for statement reconciliation."
          action={{ label: "Create bank account", onClick: () => navigate(ROUTES.ACCOUNT_CREATE) }}
        />
      ) : (
        <>
          <TableShell>
            <thead>
              <tr>
                <Th>Account</Th>
                <Th>Bank</Th>
                <Th>Type</Th>
                <Th>Last statement</Th>
                <Th>Open items</Th>
                <Th>Actions</Th>
              </tr>
            </thead>
            <tbody>
              {result.items.map((account) => (
                <tr key={account.id}>
                  <Td>
                    <Link
                      className="font-medium text-primary hover:underline"
                      to={ROUTES.ACCOUNT_DETAIL(account.id)}
                    >
                      {account.account_name}
                    </Link>
                    <div className="font-mono text-xs text-muted-foreground">
                      {account.masked_account_number.length > 0
                        ? account.masked_account_number
                        : `•••• ${account.account_number_last4}`}
                    </div>
                  </Td>
                  <Td>
                    {account.bank_name}
                    <div className="text-xs text-muted-foreground">{account.currency}</div>
                  </Td>
                  <Td>
                    <StatusPill value={account.account_type} />
                  </Td>
                  <Td>{account.last_statement_date ?? "No statements"}</Td>
                  <Td>{account.unreconciled_count}</Td>
                  <Td>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={!account.is_active || archive.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Archive ${account.account_name}? Financial history will remain available.`
                          )
                        )
                          archive.mutate(account.id);
                      }}
                    >
                      <Archive className="mr-1 h-4 w-4" />
                      Archive
                    </Button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </TableShell>
          <Pager
            result={result}
            page={filters.page ?? 1}
            onPage={(page) => setFilters({ ...filters, page })}
          />
        </>
      )}
    </Page>
  );
}

export function CreateBankAccountPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [form, setForm] = useState<BankAccountCreate>({
    account_number: "",
    bank_name: "",
    account_name: "",
    account_type: "checking",
    currency: "USD",
    opening_balance: "0.0000",
    opening_balance_date: null,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const health = useQuery({
    queryKey: ["bank-reconciliation", "health"],
    queryFn: service.health,
    retry: false,
  });
  const mutation = useMutation({
    mutationFn: service.createBankAccount,
    onSuccess: (account) => {
      void client.invalidateQueries({ queryKey: QUERY_KEYS.accounts.all });
      toast.success("Bank account created.");
      navigate(ROUTES.ACCOUNT_DETAIL(account.id));
    },
    onError: (error: Error) =>
      toast.error(
        error instanceof ApiError && error.correlationId
          ? `${error.message} (${error.correlationId})`
          : error.message
      ),
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const next = {
      account_number: required(form.account_number),
      bank_name: required(form.bank_name),
      account_name: required(form.account_name),
      currency: /^[A-Z]{3}$/.test(form.currency)
        ? undefined
        : "Use a three-letter uppercase currency code.",
    };
    const validErrors = Object.fromEntries(
      Object.entries(next).filter((entry): entry is [string, string] => Boolean(entry[1]))
    );
    setErrors(validErrors);
    if (!Object.keys(validErrors).length) mutation.mutate(form);
  };
  return (
    <Page
      title="Create bank account"
      description="Account identifiers are normalized, hashed per tenant, and masked after creation."
      actions={
        <Button variant="ghost" onClick={() => navigate(ROUTES.ACCOUNTS)}>
          <ArrowLeft className="mr-1 h-4 w-4" />
          Accounts
        </Button>
      }
    >
      <FormCard
        title="Account details"
        pending={mutation.isPending}
        submitLabel="Create account"
        onSubmit={submit}
      >
        <div className="grid gap-5 sm:grid-cols-2">
          <Field
            label="Account number"
            htmlFor="account-number"
            error={errors.account_number}
            hint="Spaces and dashes are ignored when detecting duplicates."
          >
            <Input
              id="account-number"
              autoComplete="off"
              value={form.account_number}
              onChange={(e) => setForm({ ...form, account_number: e.target.value })}
            />
          </Field>
          <Field label="Account display name" htmlFor="account-name" error={errors.account_name}>
            <Input
              id="account-name"
              value={form.account_name}
              onChange={(e) => setForm({ ...form, account_name: e.target.value })}
            />
          </Field>
          <Field label="Bank name" htmlFor="bank-name" error={errors.bank_name}>
            <Input
              id="bank-name"
              value={form.bank_name}
              onChange={(e) => setForm({ ...form, bank_name: e.target.value })}
            />
          </Field>
          <Field label="Account type" htmlFor="account-type">
            <select
              id="account-type"
              className="h-10 w-full rounded-md border bg-background px-3"
              value={form.account_type}
              onChange={(e) => setForm({ ...form, account_type: e.target.value as AccountType })}
            >
              {["checking", "savings", "credit", "cash", "other"].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </Field>
          <Field label="Currency" htmlFor="currency" error={errors.currency}>
            <Input
              id="currency"
              maxLength={3}
              value={form.currency}
              onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
            />
          </Field>
          <Field label="Opening balance" htmlFor="opening-balance">
            <Input
              id="opening-balance"
              inputMode="decimal"
              value={form.opening_balance}
              onChange={(e) => setForm({ ...form, opening_balance: e.target.value })}
            />
          </Field>
          <Field
            label="Opening balance date"
            htmlFor="opening-date"
            hint="Required when opening balance is non-zero."
          >
            <Input
              id="opening-date"
              type="date"
              value={form.opening_balance_date ?? ""}
              onChange={(e) => setForm({ ...form, opening_balance_date: e.target.value || null })}
            />
          </Field>
        </div>
        {health.data?.components.ledger_gateway === "available" ? (
          <Field
            label="Ledger account ID"
            htmlFor="ledger-account"
            hint="Validated through the tenant-scoped accounting service contract."
          >
            <Input
              id="ledger-account"
              value={form.ledger_account_id ?? ""}
              onChange={(e) => setForm({ ...form, ledger_account_id: e.target.value || null })}
            />
          </Field>
        ) : (
          <div className="rounded-md border border-dashed p-4">
            <p className="font-medium">Accounting integration disconnected</p>
            <p className="text-sm text-muted-foreground">
              You can reconcile with the core manual workflow. A ledger account can be linked later
              when a compatible integration is available.
            </p>
          </div>
        )}
      </FormCard>
    </Page>
  );
}

export function BankAccountDetailPage() {
  const id = getId(useParams().id);
  const navigate = useNavigate();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: QUERY_KEYS.accounts.detail(id),
    queryFn: () => service.getBankAccount(id),
    enabled: Boolean(id),
  });
  const archive = useMutation({
    mutationFn: () => service.archiveBankAccount(id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: QUERY_KEYS.accounts.all });
      toast.success("Account archived.");
      navigate(ROUTES.ACCOUNTS);
    },
    onError: (error: Error) => toast.error(error.message),
  });
  if (query.isLoading) return <LoadingPage title="Account details" />;
  if (query.error)
    return (
      <ErrorPage title="Account details" error={query.error} retry={() => void query.refetch()} />
    );
  if (!query.data)
    return (
      <EmptyPanel
        title="Account not found"
        description="The account may have been archived or is outside your tenant."
      />
    );
  const account = query.data;
  return (
    <Page
      title={account.account_name}
      description={`${account.bank_name} · ${account.masked_account_number}`}
      actions={
        <>
          <Button variant="outline" onClick={() => navigate(ROUTES.ACCOUNT_EDIT(id))}>
            Edit
          </Button>
          <Button
            variant="danger"
            disabled={!account.is_active || account.active_session_count > 0 || archive.isPending}
            onClick={() => archive.mutate()}
          >
            <Archive className="mr-2 h-4 w-4" />
            Archive
          </Button>
        </>
      }
    >
      <DetailGrid
        items={[
          {
            label: "Opening balance",
            value: <Money value={account.opening_balance} currency={account.currency} />,
          },
          { label: "Last statement", value: account.last_statement_date ?? "None" },
          { label: "Statements", value: account.statement_count },
          { label: "Unreconciled items", value: account.unreconciled_count },
        ]}
      />
      {account.active_session_count > 0 && (
        <Card className="border-amber-500/50">
          <CardContent className="pt-6 text-sm">
            This account has an active reconciliation and cannot be archived.
          </CardContent>
        </Card>
      )}
      <div className="grid gap-4 lg:grid-cols-3">
        {(
          [
            [
              "Recent statements",
              ROUTES.STATEMENTS,
              "Review imported and manually entered statement periods.",
            ],
            ["Imports", ROUTES.IMPORTS, "Track durable ingestion jobs and row diagnostics."],
            [
              "Reconciliations",
              ROUTES.RECONCILIATIONS,
              "Continue open work or review certified evidence.",
            ],
          ] satisfies readonly (readonly [string, string, string])[]
        ).map(([title, to, description]) => (
          <Card key={title}>
            <CardHeader>
              <CardTitle className="text-lg">{title}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-4 text-sm text-muted-foreground">{description}</p>
              <Button variant="outline" onClick={() => navigate(to)}>
                Open
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </Page>
  );
}

export function EditBankAccountPage() {
  const id = getId(useParams().id);
  const navigate = useNavigate();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: QUERY_KEYS.accounts.detail(id),
    queryFn: () => service.getBankAccount(id),
    enabled: Boolean(id),
  });
  const [form, setForm] = useState<BankAccountUpdate | null>(null);
  const current =
    form ??
    (query.data
      ? {
          bank_name: query.data.bank_name,
          account_name: query.data.account_name,
          account_type: query.data.account_type,
          bank_identifier: query.data.bank_identifier,
          ledger_account_id: query.data.ledger_account_id,
        }
      : null);
  const mutation = useMutation({
    mutationFn: (data: BankAccountUpdate) => service.updateBankAccount(id, data),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: QUERY_KEYS.accounts.all });
      toast.success("Account updated.");
      navigate(ROUTES.ACCOUNT_DETAIL(id));
    },
    onError: (error: Error) => toast.error(error.message),
  });
  if (query.isLoading || !current) return <LoadingPage title="Edit bank account" />;
  if (query.error)
    return (
      <ErrorPage title="Edit bank account" error={query.error} retry={() => void query.refetch()} />
    );
  return (
    <Page
      title="Edit bank account"
      description="Account identity and currency are locked once statement history exists."
    >
      <FormCard
        title="Mutable account fields"
        pending={mutation.isPending}
        submitLabel="Save changes"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate(current);
        }}
      >
        <Field label="Account name" htmlFor="edit-account-name">
          <Input
            id="edit-account-name"
            value={current.account_name}
            onChange={(e) => setForm({ ...current, account_name: e.target.value })}
          />
        </Field>
        <Field label="Bank name" htmlFor="edit-bank-name">
          <Input
            id="edit-bank-name"
            value={current.bank_name}
            onChange={(e) => setForm({ ...current, bank_name: e.target.value })}
          />
        </Field>
        <div className="rounded-md bg-muted p-4 text-sm">
          <strong>Locked:</strong> {query.data?.masked_account_number} · {query.data?.currency}. To
          correct an identity after activity exists, archive this account and create a replacement.
        </div>
      </FormCard>
    </Page>
  );
}

export function StatementListPage() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<StatementFilters>({ page: 1, page_size: 25 });
  const query = useQuery({
    queryKey: QUERY_KEYS.statements.list(filters),
    queryFn: () => service.listStatements(filters),
  });
  if (query.isLoading) return <LoadingPage title="Bank statements" />;
  if (query.error)
    return (
      <ErrorPage title="Bank statements" error={query.error} retry={() => void query.refetch()} />
    );
  const result = query.data;
  return (
    <Page
      title="Bank statements"
      description="Statement arithmetic, import provenance, and reconciliation status in one place."
      actions={
        <>
          <Button variant="outline" onClick={() => navigate(ROUTES.STATEMENT_CREATE)}>
            Manual statement
          </Button>
          <Button onClick={() => navigate(ROUTES.STATEMENT_IMPORT)}>
            <Upload className="mr-2 h-4 w-4" />
            Import statement
          </Button>
        </>
      }
    >
      <Card>
        <CardContent className="grid gap-3 pt-6 md:grid-cols-4">
          <select
            aria-label="Statement status"
            className="h-10 rounded-md border bg-background px-3"
            value={filters.status ?? ""}
            onChange={(e) =>
              setFilters({
                ...filters,
                status: optionalValue(e.target.value as NonNullable<StatementFilters["status"]>),
                page: 1,
              })
            }
          >
            <option value="">Any status</option>
            {["imported", "reconciling", "reconciled", "void"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
          <Input
            aria-label="Period starts after"
            type="date"
            value={filters.period_start_after ?? ""}
            onChange={(e) =>
              setFilters({ ...filters, period_start_after: optionalValue(e.target.value), page: 1 })
            }
          />
          <Input
            aria-label="Period ends before"
            type="date"
            value={filters.period_end_before ?? ""}
            onChange={(e) =>
              setFilters({ ...filters, period_end_before: optionalValue(e.target.value), page: 1 })
            }
          />
          <label className="flex items-center gap-2 rounded-md border px-3">
            <input
              type="checkbox"
              checked={filters.has_variance ?? false}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  has_variance: e.target.checked ? true : undefined,
                  page: 1,
                })
              }
            />
            Has variance
          </label>
        </CardContent>
      </Card>
      {!result?.items.length ? (
        <EmptyPanel
          title="No statements found"
          description="Import a supported bank file or enter a statement manually."
          action={{ label: "Import statement", onClick: () => navigate(ROUTES.STATEMENT_IMPORT) }}
        />
      ) : (
        <>
          <TableShell>
            <thead>
              <tr>
                <Th>Statement</Th>
                <Th>Period</Th>
                <Th>Balance proof</Th>
                <Th>Import</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {result.items.map((statement) => (
                <tr key={statement.id}>
                  <Td>
                    <Link
                      className="font-medium text-primary hover:underline"
                      to={ROUTES.STATEMENT_DETAIL(statement.id)}
                    >
                      {statement.statement_reference}
                    </Link>
                    <div className="text-xs text-muted-foreground">
                      {statement.transaction_count} transactions
                    </div>
                  </Td>
                  <Td>
                    {statement.period_start}
                    <br />
                    {statement.period_end}
                  </Td>
                  <Td>
                    <Money value={statement.closing_balance} />
                    <div
                      className={
                        statement.balance_variance === "0.0000"
                          ? "text-xs text-emerald-600"
                          : "text-xs text-destructive"
                      }
                    >
                      Variance {statement.balance_variance}
                    </div>
                  </Td>
                  <Td>
                    {statement.statement_import ? (
                      <StatusPill value={statement.statement_import.status} />
                    ) : (
                      "Manual"
                    )}
                  </Td>
                  <Td>
                    <StatusPill value={statement.status} />
                  </Td>
                </tr>
              ))}
            </tbody>
          </TableShell>
          <Pager
            result={result}
            page={filters.page ?? 1}
            onPage={(page) => setFilters({ ...filters, page })}
          />
        </>
      )}
    </Page>
  );
}

export function CreateManualStatementPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [form, setForm] = useState<ManualStatementCreate>({
    bank_account: "",
    statement_reference: "",
    period_start: "",
    period_end: "",
    opening_balance: "0.0000",
    closing_balance: "0.0000",
    transactions: [{ transaction_date: "", description: "", amount: "0.0000" }],
  });
  const total = fixedAdd(form.transactions.map((row) => row.amount));
  const calculated = fixedAdd([form.opening_balance, total]);
  const variance = fixedAdd([
    form.closing_balance,
    calculated.startsWith("-") ? calculated.slice(1) : `-${calculated}`,
  ]);
  const mutation = useMutation({
    mutationFn: service.createManualStatement,
    onSuccess: (statement) => {
      void client.invalidateQueries({ queryKey: QUERY_KEYS.statements.all });
      toast.success("Manual statement created.");
      navigate(ROUTES.STATEMENT_DETAIL(statement.id));
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const updateRow = (index: number, patch: Partial<ManualTransactionInput>) =>
    setForm({
      ...form,
      transactions: form.transactions.map((row, rowIndex) =>
        rowIndex === index ? { ...row, ...patch } : row
      ),
    });
  return (
    <Page
      title="Create manual statement"
      description="Header and transaction rows are committed atomically; the live proof uses exact fixed-point arithmetic."
    >
      <FormCard
        title="Statement and transactions"
        pending={mutation.isPending}
        submitLabel="Create statement"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate(form);
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Bank account ID" htmlFor="manual-account">
            <Input
              id="manual-account"
              value={form.bank_account}
              onChange={(e) => setForm({ ...form, bank_account: e.target.value })}
            />
          </Field>
          <Field label="Statement reference" htmlFor="manual-reference">
            <Input
              id="manual-reference"
              value={form.statement_reference}
              onChange={(e) => setForm({ ...form, statement_reference: e.target.value })}
            />
          </Field>
          <Field label="Period start" htmlFor="period-start">
            <Input
              id="period-start"
              type="date"
              value={form.period_start}
              onChange={(e) => setForm({ ...form, period_start: e.target.value })}
            />
          </Field>
          <Field label="Period end" htmlFor="period-end">
            <Input
              id="period-end"
              type="date"
              value={form.period_end}
              onChange={(e) => setForm({ ...form, period_end: e.target.value })}
            />
          </Field>
          <Field label="Opening balance" htmlFor="opening">
            <Input
              id="opening"
              inputMode="decimal"
              value={form.opening_balance}
              onChange={(e) => setForm({ ...form, opening_balance: e.target.value })}
            />
          </Field>
          <Field label="Closing balance" htmlFor="closing">
            <Input
              id="closing"
              inputMode="decimal"
              value={form.closing_balance}
              onChange={(e) => setForm({ ...form, closing_balance: e.target.value })}
            />
          </Field>
        </div>
        <div className="space-y-3">
          <div className="flex justify-between">
            <h3 className="font-semibold">Transaction rows</h3>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                setForm({
                  ...form,
                  transactions: [
                    ...form.transactions,
                    { transaction_date: form.period_end, description: "", amount: "0.0000" },
                  ],
                })
              }
            >
              <Plus className="mr-1 h-4 w-4" />
              Add row
            </Button>
          </div>
          {form.transactions.map((row, index) => (
            <div
              className="grid gap-2 rounded-md border p-3 sm:grid-cols-[140px_1fr_140px_auto]"
              key={index}
            >
              <Input
                aria-label={`Transaction ${index + 1} date`}
                type="date"
                value={row.transaction_date}
                onChange={(e) => updateRow(index, { transaction_date: e.target.value })}
              />
              <Input
                aria-label={`Transaction ${index + 1} description`}
                placeholder="Description"
                value={row.description}
                onChange={(e) => updateRow(index, { description: e.target.value })}
              />
              <Input
                aria-label={`Transaction ${index + 1} amount`}
                inputMode="decimal"
                value={row.amount}
                onChange={(e) => updateRow(index, { amount: e.target.value })}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Remove transaction ${index + 1}`}
                disabled={form.transactions.length === 1}
                onClick={() =>
                  setForm({
                    ...form,
                    transactions: form.transactions.filter((_, i) => i !== index),
                  })
                }
              >
                <XCircle className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
        <DetailGrid
          items={[
            { label: "Transaction total", value: total },
            { label: "Calculated close", value: calculated },
            { label: "Statement close", value: form.closing_balance },
            { label: "Variance", value: variance },
          ]}
        />
      </FormCard>
    </Page>
  );
}

export function ImportStatementPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [account, setAccount] = useState("");
  const [format, setFormat] = useState<Exclude<ParserFormat, "manual">>("csv");
  const [mapping, setMapping] = useState({
    date: "date",
    description: "description",
    amount: "amount",
  });
  const mutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("Choose a statement file.");
      return service.requestImport({
        bank_account: account,
        file,
        file_format: format,
        mapping: format === "csv" ? mapping : undefined,
        idempotency_key: idempotencyKey(),
      });
    },
    onSuccess: ({ import: acceptedImport }) => {
      void client.invalidateQueries({ queryKey: QUERY_KEYS.imports.all });
      toast.success("Import accepted. Processing continues as a durable job.");
      navigate(ROUTES.IMPORT_DETAIL(acceptedImport.id));
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const selectFile = (selected: File | null) => {
    setFile(selected);
    if (!selected) return;
    const extension = selected.name.split(".").pop()?.toLowerCase();
    const detected: Record<string, Exclude<ParserFormat, "manual">> = {
      csv: "csv",
      ofx: "ofx",
      qif: "qif",
      bai: "bai2",
      bai2: "bai2",
      mt940: "mt940",
      sta: "mt940",
      xml: "camt053",
    };
    const detectedFormat = extension ? detected[extension] : undefined;
    if (detectedFormat) setFormat(detectedFormat);
  };
  const drop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    selectFile(event.dataTransfer.files.item(0));
  };
  return (
    <Page
      title="Import bank statement"
      description="CSV, OFX, QIF, BAI2, MT940, and CAMT.053 run through replay-safe parser adapters."
    >
      <FormCard
        title="Upload statement"
        pending={mutation.isPending}
        submitLabel="Request import"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <Field label="Bank account ID" htmlFor="import-account">
          <Input id="import-account" value={account} onChange={(e) => setAccount(e.target.value)} />
        </Field>
        <div
          role="button"
          tabIndex={0}
          aria-label="Statement file drop zone"
          className="rounded-lg border-2 border-dashed p-8 text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onDragOver={(e) => e.preventDefault()}
          onDrop={drop}
          onKeyDown={(e) => {
            if (e.key === "Enter") document.getElementById("statement-file")?.click();
          }}
        >
          <Upload className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
          <p className="font-medium">Drop a statement file here</p>
          <p className="mb-4 text-xs text-muted-foreground">
            Maximum limits are enforced before durable job creation. Files are uploaded as multipart
            data, never base64.
          </p>
          <Input
            id="statement-file"
            className="mx-auto max-w-sm"
            type="file"
            accept=".csv,.ofx,.qif,.bai,.bai2,.sta,.xml"
            onChange={(e: ChangeEvent<HTMLInputElement>) =>
              selectFile(e.target.files?.item(0) ?? null)
            }
          />
          {file && (
            <p className="mt-3 text-sm">
              {file.name} · {(file.size / 1024).toFixed(1)} KiB
            </p>
          )}
        </div>
        <Field label="Detected format" htmlFor="file-format">
          <select
            id="file-format"
            className="h-10 w-full rounded-md border bg-background px-3"
            value={format}
            onChange={(e) => setFormat(e.target.value as Exclude<ParserFormat, "manual">)}
          >
            {["csv", "ofx", "qif", "bai2", "mt940", "camt053"].map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </Field>
        {format === "csv" && (
          <Card className="bg-muted/20">
            <CardHeader>
              <CardTitle className="text-base">CSV column mapping</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-3">
              {(["date", "description", "amount"] as const).map((field) => (
                <Field
                  key={field}
                  label={field[0]?.toUpperCase() + field.slice(1)}
                  htmlFor={`mapping-${field}`}
                >
                  <Input
                    id={`mapping-${field}`}
                    value={mapping[field]}
                    onChange={(e) => setMapping({ ...mapping, [field]: e.target.value })}
                  />
                </Field>
              ))}
            </CardContent>
          </Card>
        )}
        <div className="rounded-md border border-amber-500/40 p-4 text-sm">
          <strong>Duplicate protection:</strong> the tenant, account, and content checksum are
          checked before a new job is accepted.
        </div>
      </FormCard>
    </Page>
  );
}

export function StatementDetailPage() {
  const id = getId(useParams().id);
  const navigate = useNavigate();
  const client = useQueryClient();
  const [reason, setReason] = useState("");
  const statementQuery = useQuery({
    queryKey: QUERY_KEYS.statements.detail(id),
    queryFn: () => service.getStatement(id),
    enabled: Boolean(id),
  });
  const txFilters: TransactionFilters = { page: 1, page_size: 100 };
  const transactions = useQuery({
    queryKey: ["bank-reconciliation", "statements", id, "transactions"],
    queryFn: () => service.listStatementTransactions(id, txFilters),
    enabled: Boolean(id),
  });
  const voidMutation = useMutation({
    mutationFn: () => service.voidStatement(id, { reason, idempotency_key: idempotencyKey() }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: QUERY_KEYS.statements.all });
      toast.success("Statement voided with audit evidence.");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  if (statementQuery.isLoading) return <LoadingPage title="Statement details" />;
  if (statementQuery.error)
    return (
      <ErrorPage
        title="Statement details"
        error={statementQuery.error}
        retry={() => void statementQuery.refetch()}
      />
    );
  if (!statementQuery.data)
    return <EmptyPanel title="Statement not found" description="This statement is unavailable." />;
  const statement = statementQuery.data;
  return (
    <Page
      title={statement.statement_reference}
      description={`${statement.period_start} – ${statement.period_end}`}
      actions={
        <Button
          disabled={statement.status !== "imported"}
          onClick={() => navigate(`${ROUTES.RECONCILIATION_CREATE}?statement=${id}`)}
        >
          Create reconciliation
        </Button>
      }
    >
      <DetailGrid
        items={[
          { label: "Opening balance", value: <Money value={statement.opening_balance} /> },
          { label: "Transaction total", value: <Money value={statement.transaction_total} /> },
          {
            label: "Calculated close",
            value: <Money value={statement.calculated_closing_balance} />,
          },
          { label: "Variance", value: <Money value={statement.balance_variance} /> },
        ]}
      />
      {statement.balance_variance !== "0.0000" && (
        <Card className="border-destructive/50">
          <CardContent className="pt-6 text-sm">
            <strong>Balance proof failed.</strong> Reconciliation cannot be certified until the
            statement arithmetic is resolved.
          </CardContent>
        </Card>
      )}
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Transactions</h2>
        {transactions.isLoading ? (
          <LoadingPage title="Transactions" />
        ) : !transactions.data?.items.length ? (
          <EmptyPanel
            title="No transactions"
            description="This statement contains no transaction lines."
          />
        ) : (
          <TableShell>
            <thead>
              <tr>
                <Th>Date</Th>
                <Th>Description</Th>
                <Th>Reference</Th>
                <Th>Amount</Th>
                <Th>Match</Th>
              </tr>
            </thead>
            <tbody>
              {transactions.data.items.map((transaction) => (
                <tr key={transaction.id}>
                  <Td>{transaction.transaction_date}</Td>
                  <Td>
                    <Link
                      className="font-medium text-primary hover:underline"
                      to={ROUTES.TRANSACTION_DETAIL(transaction.id)}
                    >
                      {transaction.description}
                    </Link>
                  </Td>
                  <Td>{transaction.reference_number || "—"}</Td>
                  <Td>
                    <Money value={transaction.amount} />
                  </Td>
                  <Td>
                    <StatusPill value={transaction.match_status} />
                  </Td>
                </tr>
              ))}
            </tbody>
          </TableShell>
        )}
      </section>
      {statement.statement_import && (
        <Card>
          <CardHeader>
            <CardTitle>Import diagnostics</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <p>
              <StatusPill value={statement.statement_import.status} />{" "}
              {statement.statement_import.source_filename}
            </p>
            <p className="mt-2 text-muted-foreground">
              {statement.statement_import.rows_imported} imported ·{" "}
              {statement.statement_import.rows_rejected} rejected
            </p>
          </CardContent>
        </Card>
      )}
      {statement.status !== "reconciled" && statement.status !== "void" && (
        <Card>
          <CardHeader>
            <CardTitle>Void statement</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 sm:flex-row">
            <Input
              aria-label="Void reason"
              placeholder="Required audit reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <Button
              variant="danger"
              disabled={!reason.trim() || voidMutation.isPending}
              onClick={() => voidMutation.mutate()}
            >
              Void statement
            </Button>
          </CardContent>
        </Card>
      )}
    </Page>
  );
}

export function TransactionDetailPage() {
  const id = getId(useParams().id);
  const navigate = useNavigate();
  const client = useQueryClient();
  const [reason, setReason] = useState("");
  const query = useQuery({
    queryKey: QUERY_KEYS.transactions.detail(id),
    queryFn: () => service.getTransaction(id),
    enabled: Boolean(id),
  });
  const statusMutation = useMutation({
    mutationFn: () =>
      query.data?.match_status === "excluded"
        ? service.restoreTransaction(id)
        : service.excludeTransaction(id, { reason }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: QUERY_KEYS.transactions.all });
      setReason("");
      toast.success(
        query.data?.match_status === "excluded"
          ? "Transaction restored to unmatched."
          : "Transaction excluded with audit evidence."
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });
  if (query.isLoading) return <LoadingPage title="Transaction details" />;
  if (query.error)
    return (
      <ErrorPage
        title="Transaction details"
        error={query.error}
        retry={() => void query.refetch()}
      />
    );
  if (!query.data)
    return (
      <EmptyPanel title="Transaction not found" description="This transaction is unavailable." />
    );
  const transaction = query.data;
  return (
    <Page
      title={transaction.description}
      description={`${transaction.transaction_date} · ${transaction.reference_number || "No reference"}`}
      actions={
        transaction.source === "manual" ? (
          <Button variant="outline" onClick={() => navigate(ROUTES.TRANSACTION_EDIT(id))}>
            Edit manual transaction
          </Button>
        ) : undefined
      }
    >
      <DetailGrid
        items={[
          { label: "Amount", value: <Money value={transaction.amount} /> },
          { label: "Type", value: <StatusPill value={transaction.transaction_type} /> },
          { label: "Match status", value: <StatusPill value={transaction.match_status} /> },
          { label: "Running balance", value: transaction.running_balance ?? "Not supplied" },
        ]}
      />
      <Card>
        <CardHeader>
          <CardTitle>Normalized source fields</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            {Object.entries(transaction.source_data).map(([key, value]) => (
              <div key={key}>
                <dt className="text-xs uppercase text-muted-foreground">
                  {key.replaceAll("_", " ")}
                </dt>
                <dd>{String(value ?? "—")}</dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Match history</CardTitle>
        </CardHeader>
        <CardContent>
          {!transaction.match_history?.length ? (
            <p className="text-sm text-muted-foreground">No proposals or confirmed matches.</p>
          ) : (
            <ul className="space-y-3">
              {transaction.match_history.map((entry) => (
                <li className="flex justify-between border-b pb-2" key={entry.id}>
                  <span>
                    <StatusPill value={entry.status} /> {entry.match_type}
                  </span>
                  <Money value={entry.allocated_amount} />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      {!transaction.is_reconciled && (
        <Card>
          <CardHeader>
            <CardTitle>
              {transaction.match_status === "excluded"
                ? "Restore transaction"
                : "Exclude transaction"}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 sm:flex-row">
            {transaction.match_status !== "excluded" && (
              <Input
                aria-label="Exclusion reason"
                placeholder="Required audit reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            )}
            <Button
              variant={transaction.match_status === "excluded" ? "outline" : "danger"}
              disabled={
                statusMutation.isPending ||
                (transaction.match_status !== "excluded" && !reason.trim())
              }
              onClick={() => statusMutation.mutate()}
            >
              {transaction.match_status === "excluded"
                ? "Restore to unmatched"
                : "Exclude transaction"}
            </Button>
          </CardContent>
        </Card>
      )}
    </Page>
  );
}

export function EditTransactionPage() {
  const id = getId(useParams().id);
  const navigate = useNavigate();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: QUERY_KEYS.transactions.detail(id),
    queryFn: () => service.getTransaction(id),
    enabled: Boolean(id),
  });
  const [form, setForm] = useState<ManualTransactionInput | null>(null);
  const current =
    form ??
    (query.data
      ? {
          transaction_date: query.data.transaction_date,
          value_date: query.data.value_date,
          description: query.data.description,
          amount: query.data.amount,
          reference_number: query.data.reference_number,
          counterparty_name: query.data.counterparty_name,
        }
      : null);
  const mutation = useMutation({
    mutationFn: (payload: ManualTransactionInput) => service.updateManualTransaction(id, payload),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: QUERY_KEYS.transactions.all });
      toast.success("Manual transaction updated.");
      navigate(ROUTES.TRANSACTION_DETAIL(id));
    },
    onError: (error: Error) => toast.error(error.message),
  });
  if (query.isLoading || !current) return <LoadingPage title="Edit transaction" />;
  if (query.error)
    return (
      <ErrorPage title="Edit transaction" error={query.error} retry={() => void query.refetch()} />
    );
  if (query.data?.source !== "manual")
    return (
      <Page title="Imported transaction is immutable">
        <Card>
          <CardContent className="pt-6 text-sm">
            Source values from an imported statement cannot be edited. Exclude the line with an
            audit reason or correct and re-import the source statement.
          </CardContent>
        </Card>
      </Page>
    );
  return (
    <Page title="Edit manual transaction">
      <FormCard
        title="Transaction fields"
        pending={mutation.isPending}
        submitLabel="Save transaction"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate(current);
        }}
      >
        <Field label="Transaction date" htmlFor="edit-tx-date">
          <Input
            id="edit-tx-date"
            type="date"
            value={current.transaction_date}
            onChange={(e) => setForm({ ...current, transaction_date: e.target.value })}
          />
        </Field>
        <Field label="Description" htmlFor="edit-tx-description">
          <Input
            id="edit-tx-description"
            value={current.description}
            onChange={(e) => setForm({ ...current, description: e.target.value })}
          />
        </Field>
        <Field label="Amount" htmlFor="edit-tx-amount">
          <Input
            id="edit-tx-amount"
            value={current.amount}
            onChange={(e) => setForm({ ...current, amount: e.target.value })}
          />
        </Field>
        <Field label="Reference" htmlFor="edit-tx-reference">
          <Input
            id="edit-tx-reference"
            value={current.reference_number ?? ""}
            onChange={(e) => setForm({ ...current, reference_number: e.target.value })}
          />
        </Field>
      </FormCard>
    </Page>
  );
}

export function ReconciliationListPage() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<ReconciliationFilters>({ page: 1, page_size: 25 });
  const query = useQuery({
    queryKey: QUERY_KEYS.reconciliations.list(filters),
    queryFn: () => service.listReconciliations(filters),
  });
  if (query.isLoading) return <LoadingPage title="Reconciliations" />;
  if (query.error)
    return (
      <ErrorPage title="Reconciliations" error={query.error} retry={() => void query.refetch()} />
    );
  const result = query.data;
  return (
    <Page
      title="Reconciliations"
      description="Work in progress and certified period evidence, with variance visible at a glance."
      actions={
        <Button onClick={() => navigate(ROUTES.RECONCILIATION_CREATE)}>
          <Plus className="mr-2 h-4 w-4" />
          New reconciliation
        </Button>
      }
    >
      <Card>
        <CardContent className="grid gap-3 pt-6 md:grid-cols-4">
          <select
            aria-label="Reconciliation status"
            className="h-10 rounded-md border bg-background px-3"
            value={filters.status ?? ""}
            onChange={(e) =>
              setFilters({
                ...filters,
                status: optionalValue(e.target.value as ReconciliationStatus),
                page: 1,
              })
            }
          >
            <option value="">Any status</option>
            {["draft", "in_progress", "review", "finalized", "void"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
          <Input
            aria-label="Reconciliation after"
            type="date"
            value={filters.date_after ?? ""}
            onChange={(e) =>
              setFilters({ ...filters, date_after: optionalValue(e.target.value), page: 1 })
            }
          />
          <Input
            aria-label="Reconciliation before"
            type="date"
            value={filters.date_before ?? ""}
            onChange={(e) =>
              setFilters({ ...filters, date_before: optionalValue(e.target.value), page: 1 })
            }
          />
          <label className="flex items-center gap-2 rounded-md border px-3">
            <input
              type="checkbox"
              checked={filters.has_difference ?? false}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  has_difference: e.target.checked ? true : undefined,
                  page: 1,
                })
              }
            />
            Non-zero difference
          </label>
        </CardContent>
      </Card>
      {!result?.items.length ? (
        <EmptyPanel
          title="No reconciliations found"
          description="Start with an imported or manually entered statement."
          action={{
            label: "Create reconciliation",
            onClick: () => navigate(ROUTES.RECONCILIATION_CREATE),
          }}
        />
      ) : (
        <>
          <TableShell>
            <thead>
              <tr>
                <Th>Date</Th>
                <Th>Status</Th>
                <Th>Statement</Th>
                <Th>Matched</Th>
                <Th>Difference</Th>
                <Th>Reviewer / finalizer</Th>
              </tr>
            </thead>
            <tbody>
              {result.items.map((item) => (
                <tr key={item.id}>
                  <Td>
                    <Link
                      className="font-medium text-primary hover:underline"
                      to={
                        item.status === "finalized"
                          ? ROUTES.RECONCILIATION_DETAIL(item.id)
                          : ROUTES.RECONCILIATION_WORKSPACE(item.id)
                      }
                    >
                      {item.reconciliation_date}
                    </Link>
                  </Td>
                  <Td>
                    <StatusPill value={item.status} />
                  </Td>
                  <Td>{item.bank_statement}</Td>
                  <Td>
                    <Money value={item.matched_amount} />
                  </Td>
                  <Td>
                    <Money value={item.difference} />
                  </Td>
                  <Td>{item.finalized_by_id ?? item.reviewed_by_id ?? "Unassigned"}</Td>
                </tr>
              ))}
            </tbody>
          </TableShell>
          <Pager
            result={result}
            page={filters.page ?? 1}
            onPage={(page) => setFilters({ ...filters, page })}
          />
        </>
      )}
    </Page>
  );
}

export function CreateReconciliationPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const params = new URLSearchParams(window.location.search);
  const [form, setForm] = useState<ReconciliationCreate>({
    bank_account: "",
    bank_statement: params.get("statement") ?? "",
    reconciliation_date: new Date().toISOString().slice(0, 10),
    ledger_balance: "0.0000",
    tolerance: "0.0000",
    notes: "",
    idempotency_key: idempotencyKey(),
  });
  const mutation = useMutation({
    mutationFn: service.createReconciliation,
    onSuccess: (session) => {
      void client.invalidateQueries({ queryKey: QUERY_KEYS.reconciliations.all });
      toast.success("Reconciliation draft created.");
      navigate(ROUTES.RECONCILIATION_WORKSPACE(session.id));
    },
    onError: (error: Error) => toast.error(error.message),
  });
  return (
    <Page
      title="Create reconciliation"
      description="Create an idempotent draft against one statement and a verified ledger balance."
    >
      <FormCard
        title="Reconciliation basis"
        pending={mutation.isPending}
        submitLabel="Create draft"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate(form);
        }}
      >
        <Field label="Bank account ID" htmlFor="recon-account">
          <Input
            id="recon-account"
            value={form.bank_account}
            onChange={(e) => setForm({ ...form, bank_account: e.target.value })}
          />
        </Field>
        <Field label="Statement ID" htmlFor="recon-statement">
          <Input
            id="recon-statement"
            value={form.bank_statement}
            onChange={(e) => setForm({ ...form, bank_statement: e.target.value })}
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Reconciliation date" htmlFor="recon-date">
            <Input
              id="recon-date"
              type="date"
              value={form.reconciliation_date}
              onChange={(e) => setForm({ ...form, reconciliation_date: e.target.value })}
            />
          </Field>
          <Field
            label="Verified ledger balance"
            htmlFor="ledger-balance"
            hint="Enter the authoritative balance from the owning ledger contract."
          >
            <Input
              id="ledger-balance"
              inputMode="decimal"
              value={form.ledger_balance}
              onChange={(e) => setForm({ ...form, ledger_balance: e.target.value })}
            />
          </Field>
          <Field label="Tolerance" htmlFor="recon-tolerance">
            <Input
              id="recon-tolerance"
              inputMode="decimal"
              value={form.tolerance}
              onChange={(e) => setForm({ ...form, tolerance: e.target.value })}
            />
          </Field>
        </div>
        <Field label="Notes" htmlFor="recon-notes">
          <Textarea
            id="recon-notes"
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
          />
        </Field>
        <div className="rounded-md border border-amber-500/40 p-4 text-sm">
          <strong>Ledger gateway not configured?</strong> The core workflow remains available with a
          manually verified ledger balance and explicit ledger references. No ledger result is
          fabricated.
        </div>
      </FormCard>
    </Page>
  );
}

// The workspace intentionally presents each lifecycle guard and transaction group in one audit view.
// eslint-disable-next-line complexity
export function ReconciliationWorkspacePage() {
  const id = getId(useParams().id);
  const client = useQueryClient();
  const query = useQuery({
    queryKey: QUERY_KEYS.reconciliations.detail(id),
    queryFn: () => service.getReconciliation(id),
    enabled: Boolean(id),
  });
  const [selected, setSelected] = useState<string[]>([]);
  const [ledgerId, setLedgerId] = useState("");
  const [allocation, setAllocation] = useState("0.0000");
  const accountQuery = useQuery({
    queryKey: QUERY_KEYS.accounts.detail(query.data?.bank_account ?? ""),
    queryFn: () => service.getBankAccount(query.data?.bank_account ?? ""),
    enabled: Boolean(query.data?.bank_account),
  });
  const txFilters: TransactionFilters = { page: 1, page_size: 100 };
  const txQuery = useQuery({
    queryKey: ["bank-reconciliation", "workspace", id, "transactions"],
    queryFn: () => service.listStatementTransactions(query.data?.bank_statement ?? "", txFilters),
    enabled: Boolean(query.data?.bank_statement),
  });
  const invalidate = () =>
    void client.invalidateQueries({ queryKey: QUERY_KEYS.reconciliations.detail(id) });
  const action = useMutation({
    mutationFn: async ({ kind }: { kind: "start" | "candidates" | "review" | "finalize" }) => {
      const evidence = { idempotency_key: idempotencyKey() };
      if (kind === "start") await service.startReconciliation(id, evidence);
      else if (kind === "candidates") await service.generateCandidates(id, evidence);
      else if (kind === "review") await service.submitReview(id, evidence);
      else await service.finalizeReconciliation(id, evidence);
    },
    onSuccess: () => {
      invalidate();
      void client.invalidateQueries({ queryKey: QUERY_KEYS.transactions.all });
      toast.success("Reconciliation updated.");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const match = useMutation({
    mutationFn: () => {
      const selectedTransactions = (txQuery.data?.items ?? []).filter((transaction) =>
        selected.includes(transaction.id)
      );
      const bankAmounts = selectedTransactions.map((transaction) =>
        selected.length === 1 ? allocation : transaction.amount
      );
      const total = fixedAdd(bankAmounts);
      const currency = accountQuery.data?.currency ?? "";
      return service.createManualMatch(id, {
        match_type: selected.length > 1 ? "many_to_one" : "manual",
        lines: [
          ...selectedTransactions.map((transaction, index) => ({
            side: "bank" as const,
            bank_transaction: transaction.id,
            allocated_amount: bankAmounts[index] ?? "0.0000",
            currency,
          })),
          {
            side: "ledger" as const,
            ledger_entry_id: ledgerId,
            ledger_entry_type: "other" as const,
            allocated_amount: total,
            currency,
          },
        ],
      });
    },
    onSuccess: () => {
      setSelected([]);
      setLedgerId("");
      invalidate();
      toast.success("Manual allocation group created.");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  if (query.isLoading) return <LoadingPage title="Reconciliation workspace" />;
  if (query.error)
    return (
      <ErrorPage
        title="Reconciliation workspace"
        error={query.error}
        retry={() => void query.refetch()}
      />
    );
  if (!query.data)
    return (
      <EmptyPanel title="Reconciliation not found" description="This session is unavailable." />
    );
  const session = query.data;
  if (session.status === "finalized")
    return (
      <Page title="Certified reconciliation">
        <Card>
          <CardContent className="pt-6">
            <p className="mb-4">This session is read-only after certification.</p>
            <Button onClick={() => window.location.assign(ROUTES.RECONCILIATION_DETAIL(id))}>
              View evidence
            </Button>
          </CardContent>
        </Card>
      </Page>
    );
  const groups = ["unmatched", "proposed", "matched", "excluded"] as const;
  const transactions = txQuery.data?.items ?? [];
  const guards = session.summary?.guard_failures ?? [];
  return (
    <Page
      title="Reconciliation workspace"
      description="Transparent candidate evidence and complex allocations without a spreadsheet."
      actions={
        <>
          <Button
            variant="outline"
            disabled={action.isPending || session.status !== "draft"}
            onClick={() => action.mutate({ kind: "start" })}
          >
            Start
          </Button>
          <Button
            variant="outline"
            disabled={action.isPending || session.status !== "in_progress"}
            onClick={() => action.mutate({ kind: "candidates" })}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            Generate candidates
          </Button>
        </>
      }
    >
      <div className="grid min-h-[520px] gap-4 xl:grid-cols-[1fr_1fr_320px]">
        <Card>
          <CardHeader>
            <CardTitle>Bank transactions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {groups.map((group) => {
              const rows = transactions.filter((tx) => tx.match_status === group);
              return (
                <section key={group}>
                  <h3 className="mb-2 flex justify-between text-sm font-semibold capitalize">
                    {group}
                    <span>{rows.length}</span>
                  </h3>
                  {!rows.length ? (
                    <p className="rounded border border-dashed p-3 text-xs text-muted-foreground">
                      No {group} transactions
                    </p>
                  ) : (
                    rows.map((tx) => (
                      <label
                        className="mb-2 flex cursor-pointer gap-3 rounded border p-3 focus-within:ring-2 focus-within:ring-ring"
                        key={tx.id}
                      >
                        <input
                          type="checkbox"
                          disabled={group === "matched" || group === "excluded"}
                          checked={selected.includes(tx.id)}
                          onChange={(e) =>
                            setSelected(
                              e.target.checked
                                ? [...selected, tx.id]
                                : selected.filter((value) => value !== tx.id)
                            )
                          }
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium">{tx.description}</span>
                          <span className="text-xs text-muted-foreground">
                            {tx.transaction_date} · {tx.reference_number}
                          </span>
                        </span>
                        <Money value={tx.amount} />
                      </label>
                    ))
                  )}
                </section>
              );
            })}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Ledger candidates</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-md border border-amber-500/40 p-4 text-sm">
              <strong>Live ledger candidate gateway unavailable.</strong>
              <p className="mt-1 text-muted-foreground">
                Enter a tenant-validated ledger reference below. Installations with a registered
                gateway can provide searchable immutable candidate snapshots; this core UI never
                invents candidates.
              </p>
            </div>
            {session.matches?.map((candidate) => (
              <div key={candidate.id} className="rounded border p-3">
                <div className="flex justify-between">
                  <StatusPill value={candidate.status} />
                  <span className="font-medium">Score {candidate.score ?? "manual"}</span>
                </div>
                {candidate.explanation && (
                  <div className="mt-2 flex flex-wrap gap-1 text-xs">
                    {Object.entries(candidate.explanation).map(([factor, score]) => (
                      <span className="rounded-full bg-muted px-2 py-1" key={factor}>
                        {factor}: {score}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
        <aside className="space-y-4">
          <Card className="sticky top-4">
            <CardHeader>
              <CardTitle>Reconciliation proof</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {(
                [
                  ["Statement balance", session.statement_balance],
                  ["Ledger balance", session.ledger_balance],
                  ["Matched", session.matched_amount],
                  ["Unmatched", session.unmatched_amount],
                  ["Tolerance", session.tolerance],
                  ["Difference", session.difference],
                ] satisfies readonly (readonly [string, string])[]
              ).map(([label, value]) => (
                <div className="flex justify-between border-b pb-2" key={label}>
                  <span className="text-muted-foreground">{label}</span>
                  <Money value={value} />
                </div>
              ))}
              <div>
                <StatusPill value={session.status} />
              </div>
              {guards.length > 0 && (
                <div className="rounded bg-destructive/10 p-3">
                  <p className="font-medium">Certification blocked</p>
                  <ul className="mt-1 list-disc pl-4 text-xs">
                    {guards.map((guard) => (
                      <li key={guard}>{guard}</li>
                    ))}
                  </ul>
                </div>
              )}
              <Button
                className="w-full"
                disabled={action.isPending || session.status !== "in_progress" || guards.length > 0}
                onClick={() => action.mutate({ kind: "review" })}
              >
                Submit review
              </Button>
              <Button
                className="w-full"
                disabled={action.isPending || session.status !== "review" || guards.length > 0}
                onClick={() => action.mutate({ kind: "finalize" })}
              >
                <ShieldCheck className="mr-2 h-4 w-4" />
                Finalize
              </Button>
            </CardContent>
          </Card>
        </aside>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Allocation tray</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
          <Field
            label={`Ledger entry UUID (${selected.length} bank selected)`}
            htmlFor="ledger-entry"
          >
            <Input
              id="ledger-entry"
              value={ledgerId}
              onChange={(e) => setLedgerId(e.target.value)}
            />
          </Field>
          <Field
            label={
              selected.length > 1 ? "Bank total (full selected amounts)" : "Signed allocation total"
            }
            htmlFor="allocation-total"
          >
            <Input
              id="allocation-total"
              inputMode="decimal"
              disabled={selected.length > 1}
              value={
                selected.length > 1
                  ? fixedAdd(
                      transactions
                        .filter((transaction) => selected.includes(transaction.id))
                        .map((transaction) => transaction.amount)
                    )
                  : allocation
              }
              onChange={(e) => setAllocation(e.target.value)}
            />
          </Field>
          <Button
            className="self-end"
            disabled={
              !selected.length || !ledgerId || !accountQuery.data?.currency || match.isPending
            }
            onClick={() => match.mutate()}
          >
            Create allocation
          </Button>
        </CardContent>
      </Card>
    </Page>
  );
}

export function ReconciliationDetailPage() {
  const id = getId(useParams().id);
  const query = useQuery({
    queryKey: QUERY_KEYS.reconciliations.detail(id),
    queryFn: () => service.getReconciliation(id),
    enabled: Boolean(id),
  });
  const [downloading, setDownloading] = useState(false);
  if (query.isLoading) return <LoadingPage title="Reconciliation evidence" />;
  if (query.error)
    return (
      <ErrorPage
        title="Reconciliation evidence"
        error={query.error}
        retry={() => void query.refetch()}
      />
    );
  if (!query.data)
    return <EmptyPanel title="Reconciliation not found" description="Evidence is unavailable." />;
  const session = query.data;
  const download = async () => {
    setDownloading(true);
    try {
      const blob = await service.downloadReport(id, "csv");
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `reconciliation-${id}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Export failed.");
    } finally {
      setDownloading(false);
    }
  };
  return (
    <Page
      title="Reconciliation evidence"
      description="Read-only certification facts and immutable transition history."
      actions={
        <Button disabled={downloading} onClick={() => void download()}>
          <Download className="mr-2 h-4 w-4" />
          {downloading ? "Preparing…" : "Export CSV"}
        </Button>
      }
    >
      <DetailGrid
        items={[
          { label: "Status", value: <StatusPill value={session.status} /> },
          { label: "Statement balance", value: <Money value={session.statement_balance} /> },
          { label: "Ledger balance", value: <Money value={session.ledger_balance} /> },
          { label: "Difference", value: <Money value={session.difference} /> },
        ]}
      />
      <Card>
        <CardHeader>
          <CardTitle>Transition history</CardTitle>
        </CardHeader>
        <CardContent>
          {!session.transition_history.length ? (
            <p className="text-sm text-muted-foreground">No transitions recorded.</p>
          ) : (
            <ol className="space-y-3">
              {session.transition_history.map((transition, index) => (
                <li className="border-l-2 pl-4" key={`${transition.occurred_at}-${index}`}>
                  <p className="font-medium">
                    {transition.command}: {transition.from} → {transition.to}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {transition.occurred_at} · actor {transition.actor_id}
                  </p>
                  {transition.reason && <p className="text-sm">{transition.reason}</p>}
                </li>
              ))}
            </ol>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Match evidence</CardTitle>
        </CardHeader>
        <CardContent>
          {!session.matches?.length ? (
            <p className="text-sm text-muted-foreground">No match groups recorded.</p>
          ) : (
            session.matches.map((match) => (
              <div className="mb-3 rounded border p-3" key={match.id}>
                <div className="flex justify-between">
                  <span>{match.match_type}</span>
                  <StatusPill value={match.status} />
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  {match.lines.length} allocation lines ·{" "}
                  {match.score ? `score ${match.score}` : "manual evidence"}
                </p>
                {match.status === "confirmed" && (
                  <p className="mt-2 text-xs">
                    Reversal requires a governed correction workflow and audit reason; certification
                    is never silently rewritten.
                  </p>
                )}
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </Page>
  );
}

const initialRule: MatchingRuleCreate = {
  name: "",
  description: "",
  rule_type: "exact",
  priority: 100,
  configuration: {},
  auto_confirm: false,
  minimum_score: "1.0000",
  extension_key: "",
};
function RuleForm({
  initial,
  pending,
  label,
  onSubmit,
}: {
  initial: MatchingRuleCreate;
  pending: boolean;
  label: string;
  onSubmit: (value: MatchingRuleCreate) => void;
}) {
  const [form, setForm] = useState(initial);
  const config = form.configuration;
  return (
    <FormCard
      title="Deterministic matching policy"
      pending={pending}
      submitLabel={label}
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(form);
      }}
    >
      <Field label="Rule name" htmlFor="rule-name">
        <Input
          id="rule-name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
      </Field>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Rule type" htmlFor="rule-type">
          <select
            id="rule-type"
            className="h-10 w-full rounded-md border bg-background px-3"
            value={form.rule_type}
            onChange={(e) =>
              setForm({ ...form, rule_type: e.target.value as RuleType, configuration: {} })
            }
          >
            {[
              "exact",
              "date_window",
              "reference",
              "amount_tolerance",
              "counterparty",
              "extension",
            ].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </Field>
        <Field label="Priority" htmlFor="rule-priority" hint="Lower priorities execute first.">
          <Input
            id="rule-priority"
            type="number"
            min="1"
            value={form.priority}
            onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
          />
        </Field>
        <Field label="Minimum score" htmlFor="minimum-score">
          <Input
            id="minimum-score"
            inputMode="decimal"
            value={form.minimum_score}
            onChange={(e) => setForm({ ...form, minimum_score: e.target.value })}
          />
        </Field>
      </div>
      <Field label="Description" htmlFor="rule-description">
        <Textarea
          id="rule-description"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
      </Field>
      {form.rule_type === "date_window" && (
        <Field label="Date window (days)" htmlFor="date-window">
          <Input
            id="date-window"
            type="number"
            min="0"
            value={config.date_window_days ?? 0}
            onChange={(e) =>
              setForm({
                ...form,
                configuration: { ...config, date_window_days: Number(e.target.value) },
              })
            }
          />
        </Field>
      )}
      {form.rule_type === "amount_tolerance" && (
        <Field label="Amount tolerance" htmlFor="amount-tolerance">
          <Input
            id="amount-tolerance"
            value={config.amount_tolerance ?? "0.0000"}
            onChange={(e) =>
              setForm({ ...form, configuration: { ...config, amount_tolerance: e.target.value } })
            }
          />
        </Field>
      )}
      {form.rule_type === "reference" && (
        <Field label="Reference normalization" htmlFor="reference-normalization">
          <Input
            id="reference-normalization"
            value={config.reference_normalization ?? ""}
            onChange={(e) =>
              setForm({
                ...form,
                configuration: { ...config, reference_normalization: e.target.value },
              })
            }
          />
        </Field>
      )}
      {form.rule_type === "counterparty" && (
        <Field label="Counterparty pattern" htmlFor="counterparty-pattern">
          <Input
            id="counterparty-pattern"
            value={config.counterparty_pattern ?? ""}
            onChange={(e) =>
              setForm({
                ...form,
                configuration: { ...config, counterparty_pattern: e.target.value },
              })
            }
          />
        </Field>
      )}
      {form.rule_type === "extension" && (
        <Field
          label="Extension key"
          htmlFor="extension-key"
          hint="The provider must be installed, entitled, and healthy at execution time."
        >
          <Input
            id="extension-key"
            value={form.extension_key}
            onChange={(e) => setForm({ ...form, extension_key: e.target.value })}
          />
        </Field>
      )}
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={form.auto_confirm}
          onChange={(e) =>
            setForm({
              ...form,
              auto_confirm: e.target.checked,
              minimum_score: e.target.checked ? "1.0000" : form.minimum_score,
            })
          }
        />
        Automatically confirm perfect deterministic matches
      </label>
      <Card className="bg-muted/20">
        <CardHeader>
          <CardTitle className="text-base">Safe preview</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Save the rule before candidate generation. Preview never mutates transactions; every
          proposal records amount, reference, date, counterparty, rule, and score factors.
        </CardContent>
      </Card>
    </FormCard>
  );
}

export function MatchingRuleListPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [filters, setFilters] = useState<RuleFilters>({ page: 1, page_size: 25 });
  const query = useQuery({
    queryKey: QUERY_KEYS.rules.list(filters),
    queryFn: () => service.listRules(filters),
  });
  const toggle = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      active ? service.deactivateRule(id) : service.activateRule(id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: QUERY_KEYS.rules.all });
      toast.success("Rule status updated.");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  if (query.isLoading) return <LoadingPage title="Matching rules" />;
  if (query.error)
    return (
      <ErrorPage title="Matching rules" error={query.error} retry={() => void query.refetch()} />
    );
  const result = query.data;
  return (
    <Page
      title="Matching rules"
      description="Ordered, explainable policies for deterministic candidate scoring."
      actions={
        <Button onClick={() => navigate(ROUTES.RULE_CREATE)}>
          <Plus className="mr-2 h-4 w-4" />
          New rule
        </Button>
      }
    >
      {!result?.items.length ? (
        <EmptyPanel
          title="No matching rules"
          description="Create a deterministic policy or use exact matching from the core provider."
          action={{ label: "Create rule", onClick: () => navigate(ROUTES.RULE_CREATE) }}
        />
      ) : (
        <>
          <TableShell>
            <thead>
              <tr>
                <Th>Priority</Th>
                <Th>Rule</Th>
                <Th>Type</Th>
                <Th>Minimum score</Th>
                <Th>Usage</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {result.items.map((rule) => (
                <tr key={rule.id}>
                  <Td>{rule.priority}</Td>
                  <Td>
                    <Link
                      className="font-medium text-primary hover:underline"
                      to={ROUTES.RULE_DETAIL(rule.id)}
                    >
                      {rule.name}
                    </Link>
                    {rule.extension_key && (
                      <div className="text-xs text-muted-foreground">
                        Extension: {rule.extension_key}
                      </div>
                    )}
                  </Td>
                  <Td>
                    <StatusPill value={rule.rule_type} />
                  </Td>
                  <Td>{rule.minimum_score}</Td>
                  <Td>{rule.usage_count}</Td>
                  <Td>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={toggle.isPending}
                      onClick={() => toggle.mutate({ id: rule.id, active: rule.is_active })}
                    >
                      {rule.is_active ? "Deactivate" : "Activate"}
                    </Button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </TableShell>
          <Pager
            result={result}
            page={filters.page ?? 1}
            onPage={(page) => setFilters({ ...filters, page })}
          />
        </>
      )}
    </Page>
  );
}

export function CreateMatchingRulePage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: service.createRule,
    onSuccess: (rule) => {
      void client.invalidateQueries({ queryKey: QUERY_KEYS.rules.all });
      toast.success("Matching rule created.");
      navigate(ROUTES.RULE_DETAIL(rule.id));
    },
    onError: (error: Error) => toast.error(error.message),
  });
  return (
    <Page
      title="Create matching rule"
      description="Configure a documented core rule or a namespaced extension provider."
    >
      <RuleForm
        initial={initialRule}
        pending={mutation.isPending}
        label="Create rule"
        onSubmit={(value) => mutation.mutate(value)}
      />
    </Page>
  );
}

export function MatchingRuleDetailPage() {
  const id = getId(useParams().id);
  const navigate = useNavigate();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: QUERY_KEYS.rules.detail(id),
    queryFn: () => service.getRule(id),
    enabled: Boolean(id),
  });
  const remove = useMutation({
    mutationFn: () => service.deleteRule(id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: QUERY_KEYS.rules.all });
      toast.success("Unused rule deleted.");
      navigate(ROUTES.RULES);
    },
    onError: (error: Error) =>
      toast.error(`${error.message} Deactivate rules referenced by match evidence.`),
  });
  if (query.isLoading) return <LoadingPage title="Matching rule" />;
  if (query.error)
    return (
      <ErrorPage title="Matching rule" error={query.error} retry={() => void query.refetch()} />
    );
  if (!query.data)
    return <EmptyPanel title="Rule not found" description="This rule is unavailable." />;
  const rule = query.data;
  return (
    <Page
      title={rule.name}
      description={rule.description.length > 0 ? rule.description : "No description"}
      actions={
        <>
          <Button variant="outline" onClick={() => navigate(ROUTES.RULE_EDIT(id))}>
            Edit
          </Button>
          <Button
            variant="danger"
            disabled={remove.isPending || rule.usage_count > 0}
            onClick={() => remove.mutate()}
          >
            Delete unused rule
          </Button>
        </>
      }
    >
      <DetailGrid
        items={[
          { label: "Priority", value: rule.priority },
          { label: "Type", value: <StatusPill value={rule.rule_type} /> },
          { label: "Minimum score", value: rule.minimum_score },
          { label: "Usage count", value: rule.usage_count },
        ]}
      />
      <Card>
        <CardHeader>
          <CardTitle>Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="overflow-auto rounded bg-muted p-4 text-xs">
            {JSON.stringify(rule.configuration, null, 2)}
          </pre>
          {rule.extension_key && (
            <p className="mt-3 text-sm">
              Owned by extension <code>{rule.extension_key}</code>. If unavailable, candidate
              execution fails explicitly; historical evidence remains readable.
            </p>
          )}
        </CardContent>
      </Card>
    </Page>
  );
}

export function EditMatchingRulePage() {
  const id = getId(useParams().id);
  const navigate = useNavigate();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: QUERY_KEYS.rules.detail(id),
    queryFn: () => service.getRule(id),
    enabled: Boolean(id),
  });
  const mutation = useMutation({
    mutationFn: (value: MatchingRuleUpdate) => service.updateRule(id, value),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: QUERY_KEYS.rules.all });
      toast.success("Rule updated.");
      navigate(ROUTES.RULE_DETAIL(id));
    },
    onError: (error: Error) => toast.error(error.message),
  });
  if (query.isLoading) return <LoadingPage title="Edit matching rule" />;
  if (query.error)
    return (
      <ErrorPage
        title="Edit matching rule"
        error={query.error}
        retry={() => void query.refetch()}
      />
    );
  if (!query.data)
    return <EmptyPanel title="Rule not found" description="This rule is unavailable." />;
  const rule = query.data;
  const initial: MatchingRuleCreate = {
    name: rule.name,
    description: rule.description,
    rule_type: rule.rule_type,
    priority: rule.priority,
    configuration: rule.configuration,
    auto_confirm: rule.auto_confirm,
    minimum_score: rule.minimum_score,
    extension_key: rule.extension_key,
  };
  return (
    <Page
      title="Edit matching rule"
      description="Existing match explanations remain immutable after policy changes."
    >
      <RuleForm
        initial={initial}
        pending={mutation.isPending}
        label="Save rule"
        onSubmit={(value) => mutation.mutate(value)}
      />
    </Page>
  );
}

export function ImportJobListPage() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<ImportFilters>({ page: 1, page_size: 25 });
  const query = useQuery({
    queryKey: QUERY_KEYS.imports.list(filters),
    queryFn: () => service.listImports(filters),
    refetchInterval: (state) =>
      state.state.data?.items.some((job) => job.status === "pending" || job.status === "running")
        ? 3000
        : false,
  });
  if (query.isLoading) return <LoadingPage title="Import jobs" />;
  if (query.error)
    return <ErrorPage title="Import jobs" error={query.error} retry={() => void query.refetch()} />;
  const result = query.data;
  return (
    <Page
      title="Import jobs"
      description="Durable ingestion status, bounded diagnostics, and row-level outcomes."
      actions={
        <Button onClick={() => navigate(ROUTES.STATEMENT_IMPORT)}>
          <Upload className="mr-2 h-4 w-4" />
          New import
        </Button>
      }
    >
      <Card>
        <CardContent className="grid gap-3 pt-6 sm:grid-cols-2">
          <select
            aria-label="Import status"
            className="h-10 rounded-md border bg-background px-3"
            value={filters.status ?? ""}
            onChange={(e) =>
              setFilters({
                ...filters,
                status: optionalValue(e.target.value as NonNullable<ImportFilters["status"]>),
                page: 1,
              })
            }
          >
            <option value="">Any status</option>
            {["pending", "running", "succeeded", "failed", "cancelled"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
          <select
            aria-label="File format"
            className="h-10 rounded-md border bg-background px-3"
            value={filters.file_format ?? ""}
            onChange={(e) =>
              setFilters({
                ...filters,
                file_format: optionalValue(e.target.value as ParserFormat),
                page: 1,
              })
            }
          >
            <option value="">Any format</option>
            {["csv", "ofx", "qif", "bai2", "mt940", "camt053", "manual"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </CardContent>
      </Card>
      {!result?.items.length ? (
        <EmptyPanel
          title="No import jobs"
          description="Import a bank file to create a durable, auditable job."
          action={{ label: "Import statement", onClick: () => navigate(ROUTES.STATEMENT_IMPORT) }}
        />
      ) : (
        <>
          <TableShell>
            <thead>
              <tr>
                <Th>File</Th>
                <Th>Format</Th>
                <Th>Status</Th>
                <Th>Rows</Th>
                <Th>Started</Th>
              </tr>
            </thead>
            <tbody>
              {result.items.map((job) => (
                <tr key={job.id}>
                  <Td>
                    <Link
                      className="font-medium text-primary hover:underline"
                      to={ROUTES.IMPORT_DETAIL(job.id)}
                    >
                      {job.source_filename}
                    </Link>
                  </Td>
                  <Td>{job.file_format}</Td>
                  <Td>
                    <StatusPill value={job.status} />
                  </Td>
                  <Td>
                    {job.rows_imported} imported / {job.rows_rejected} rejected
                  </Td>
                  <Td>{job.started_at ?? "Queued"}</Td>
                </tr>
              ))}
            </tbody>
          </TableShell>
          <Pager
            result={result}
            page={filters.page ?? 1}
            onPage={(page) => setFilters({ ...filters, page })}
          />
        </>
      )}
    </Page>
  );
}

export function ImportJobDetailPage() {
  const id = getId(useParams().id);
  const client = useQueryClient();
  const query = useQuery({
    queryKey: QUERY_KEYS.imports.detail(id),
    queryFn: () => service.getImport(id),
    enabled: Boolean(id),
    refetchInterval: (state) =>
      state.state.data && ["pending", "running"].includes(state.state.data.status) ? 2500 : false,
  });
  const retry = useMutation({
    mutationFn: () => service.retryImport(id, { idempotency_key: idempotencyKey() }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: QUERY_KEYS.imports.all });
      toast.success("Import retry accepted as a new durable job attempt.");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const cancel = useMutation({
    mutationFn: () => service.cancelImport(id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: QUERY_KEYS.imports.all });
      toast.success("Cancellation recorded.");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  if (query.isLoading) return <LoadingPage title="Import job" />;
  if (query.error)
    return <ErrorPage title="Import job" error={query.error} retry={() => void query.refetch()} />;
  if (!query.data)
    return <EmptyPanel title="Import not found" description="This job is unavailable." />;
  const job = query.data;
  return (
    <Page
      title={job.source_filename || "Statement import"}
      description={`Import ${job.id}`}
      actions={
        <>
          {job.status === "failed" && (
            <Button disabled={retry.isPending} onClick={() => retry.mutate()}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Retry
            </Button>
          )}
          {["pending", "running"].includes(job.status) && (
            <Button variant="danger" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
              Cancel
            </Button>
          )}
        </>
      }
    >
      <DetailGrid
        items={[
          { label: "Status", value: <StatusPill value={job.status} /> },
          { label: "Rows received", value: job.rows_received },
          { label: "Rows imported", value: job.rows_imported },
          { label: "Rows rejected", value: job.rows_rejected },
        ]}
      />
      {["pending", "running"].includes(job.status) && (
        <Card aria-live="polite">
          <CardContent className="flex items-center gap-3 pt-6">
            <RefreshCw className="h-5 w-5 animate-spin" />
            <div>
              <p className="font-medium">Processing continues in a durable worker</p>
              <p className="text-sm text-muted-foreground">
                Leaving this page does not cancel the job.
              </p>
            </div>
          </CardContent>
        </Card>
      )}
      {job.status === "failed" && (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle>Sanitized diagnostics</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-mono text-sm">{job.error_code}</p>
            <pre className="mt-3 max-h-64 overflow-auto rounded bg-muted p-3 text-xs">
              {JSON.stringify(job.error_detail, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
      {job.status === "succeeded" && (
        <Card className="border-emerald-500/50">
          <CardContent className="flex gap-3 pt-6">
            <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            <div>
              <p className="font-medium">Import succeeded</p>
              {job.statement_id && (
                <Button
                  className="mt-3"
                  variant="outline"
                  onClick={() =>
                    window.location.assign(ROUTES.STATEMENT_DETAIL(job.statement_id ?? ""))
                  }
                >
                  Open statement
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}
      {job.correlation_id && (
        <p className="font-mono text-xs text-muted-foreground">
          Correlation ID: {job.correlation_id}
        </p>
      )}
    </Page>
  );
}
