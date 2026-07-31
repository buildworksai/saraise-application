/* eslint-disable max-lines-per-function -- behavior-rich form tests cover accounting validation and derived totals. */
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  AccountForm,
  InvoiceForm,
  JournalEntryForm,
  PaymentForm,
  PostingPeriodForm,
} from "./AggregateForms";
import { Field, FormGrid, SelectField, SubmitRow, TextAreaField } from "./FormPrimitives";

const accountId = "11111111-1111-4111-8111-111111111111";
const periodId = "22222222-2222-4222-8222-222222222222";
const apInvoiceId = "33333333-3333-4333-8333-333333333333";
const arInvoiceId = "44444444-4444-4444-8444-444444444444";

function submitForm(buttonName: string) {
  const form = screen.getByRole("button", { name: buttonName }).closest("form");
  if (!form) throw new Error(`Expected ${buttonName} button to belong to a form.`);
  fireEvent.submit(form);
}

describe("accounting aggregate forms", () => {
  it("renders primitive fields with errors, state changes, and pending submit protection", async () => {
    const user = userEvent.setup();
    const selectChange = vi.fn();
    const cancel = vi.fn();

    render(
      <form>
        <FormGrid>
          <Field id="primitive-code" label="Code" error="Code is required" required />
          <SelectField
            id="primitive-select"
            label="Type"
            value="asset"
            onChange={selectChange}
            error="Choose a type"
            required
          >
            <option value="asset">Asset</option>
            <option value="liability">Liability</option>
          </SelectField>
        </FormGrid>
        <TextAreaField
          id="primitive-description"
          label="Description"
          value="Initial"
          onChange={vi.fn()}
          error="Too long"
        />
        <SubmitRow pending submitLabel="Save" onCancel={cancel} />
      </form>
    );

    expect(screen.getByLabelText("Code")).toHaveClass("border-destructive");
    expect(screen.getByText("Code is required")).toBeInTheDocument();
    expect(screen.getByLabelText("Type")).toHaveAttribute("aria-describedby", "primitive-select-error");
    await user.selectOptions(screen.getByLabelText("Type"), "liability");
    expect(selectChange).toHaveBeenCalledWith("liability");
    expect(screen.getByText("Too long")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
  });

  it("validates and submits account data with normalized currency and nullable optional fields", async () => {
    const user = userEvent.setup();
    const submit = vi.fn();
    const cancel = vi.fn();

    render(
      <AccountForm
        pending={false}
        serverErrors={{ code: "Code already exists" }}
        onSubmit={submit}
        onCancel={cancel}
      />
    );

    expect(screen.getByText("Code already exists")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Account code"), " ");
    await user.type(screen.getByLabelText("Account name"), " ");
    submitForm("Create account");
    expect(await screen.findAllByText("String must contain at least 1 character(s)")).toHaveLength(2);
    expect(submit).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Account code"));
    await user.type(screen.getByLabelText("Account code"), "1000");
    await user.clear(screen.getByLabelText("Account name"));
    await user.type(screen.getByLabelText("Account name"), "Operating Cash");
    await user.selectOptions(screen.getByLabelText("Account type"), "asset");
    await user.selectOptions(screen.getByLabelText("Normal balance"), "debit");
    await user.clear(screen.getByLabelText("Currency"));
    await user.type(screen.getByLabelText("Currency"), "usd");
    await user.selectOptions(screen.getByLabelText("Cash-flow category"), "operating");
    await user.click(screen.getByLabelText("Group account"));
    await user.click(screen.getByLabelText("Active"));
    await user.click(screen.getByLabelText("Allow multi-currency"));
    await user.type(screen.getByLabelText("Description"), "Primary bank ledger");
    submitForm("Create account");

    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        code: "1000",
        name: "Operating Cash",
        currency: "USD",
        cash_flow_category: "operating",
        is_group: true,
        is_active: false,
        allow_multi_currency: true,
        description: "Primary bank ledger",
      })
    );
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(cancel).toHaveBeenCalledOnce();
  });

  it("blocks invalid posting period dates and submits the corrected governed range", async () => {
    const user = userEvent.setup();
    const submit = vi.fn();

    render(<PostingPeriodForm pending={false} onSubmit={submit} onCancel={vi.fn()} />);

    await user.type(screen.getByLabelText("Period name"), "FY26-07");
    fireEvent.change(screen.getByLabelText("Fiscal year"), { target: { value: "2026" } });
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-07-31" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-07-01" } });
    submitForm("Create period");

    expect(await screen.findByText("End date must be on or after start date.")).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-07-31" } });
    submitForm("Create period");
    expect(submit).toHaveBeenCalledWith({
      period_name: "FY26-07",
      start_date: "2026-07-31",
      end_date: "2026-07-31",
      fiscal_year: 2026,
    });
  });

  it("enforces journal line semantics, balance, derived totals, and line re-numbering", async () => {
    const user = userEvent.setup();
    const submit = vi.fn();

    render(<JournalEntryForm pending={false} onSubmit={submit} onCancel={vi.fn()} />);

    await user.type(screen.getByLabelText("Entry number"), "JE-100");
    await user.clear(screen.getByLabelText("Posting date"));
    await user.type(screen.getByLabelText("Posting date"), "2026-07-31");
    await user.type(screen.getByLabelText("Posting period UUID"), periodId);
    await user.type(screen.getByLabelText("Line 1 account"), accountId);
    await user.type(screen.getByLabelText("Line 1 description"), "Debit cash");
    await user.clear(screen.getByLabelText("Line 1 debit"));
    await user.type(screen.getByLabelText("Line 1 debit"), "12.34");
    await user.type(screen.getByLabelText("Line 2 account"), accountId);
    await user.clear(screen.getByLabelText("Line 2 credit"));
    await user.type(screen.getByLabelText("Line 2 credit"), "10.00");
    expect(screen.getByText("Difference 2.34")).toBeInTheDocument();

    submitForm("Create draft");
    expect(await screen.findByRole("alert")).toHaveTextContent("Debits and credits must balance exactly.");
    expect(submit).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Line 2 credit"));
    await user.type(screen.getByLabelText("Line 2 credit"), "12.34");
    expect(screen.getByText("Balanced")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Line" }));
    await user.type(screen.getByLabelText("Line 3 account"), accountId);
    await user.clear(screen.getByLabelText("Line 3 debit"));
    await user.type(screen.getByLabelText("Line 3 debit"), "1.00");
    await user.click(screen.getByRole("button", { name: "Remove line 2" }));
    expect(screen.queryByLabelText("Line 3 account")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Line 2 account")).toHaveValue(accountId);
  });

  it("submits AP and AR invoices with party-specific payloads and calculated preview totals", async () => {
    const user = userEvent.setup();
    const submit = vi.fn();
    const { unmount } = render(
      <InvoiceForm kind="ap" pending={false} onSubmit={submit} onCancel={vi.fn()} />
    );

    await user.type(screen.getByLabelText("Invoice number"), "AP-100");
    await user.type(screen.getByLabelText("Supplier UUID"), accountId);
    await user.clear(screen.getByLabelText("Invoice date"));
    await user.type(screen.getByLabelText("Invoice date"), "2026-08-01");
    await user.clear(screen.getByLabelText("Due date"));
    await user.type(screen.getByLabelText("Due date"), "2026-07-31");
    await user.type(screen.getByLabelText("Line 1 description"), "Consulting");
    await user.type(screen.getByLabelText("Line 1 account"), accountId);
    await user.clear(screen.getByLabelText("Line 1 unit price"));
    await user.type(screen.getByLabelText("Line 1 unit price"), "10.00");
    await user.clear(screen.getByLabelText("Line 1 tax"));
    await user.type(screen.getByLabelText("Line 1 tax"), "1.50");
    expect(screen.getByText("USD 11.50")).toBeInTheDocument();
    submitForm("Create invoice");
    expect(await screen.findByText("Due date must be on or after invoice date.")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Due date"));
    await user.type(screen.getByLabelText("Due date"), "2026-08-31");
    submitForm("Create invoice");
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        invoice_number: "AP-100",
        supplier_id: accountId,
        lines: [expect.objectContaining({ unit_price: "10.00", tax_amount: "1.50" })],
      })
    );

    submit.mockClear();
    unmount();
    render(
      <InvoiceForm
        kind="ar"
        pending={false}
        initial={{
          invoice_number: "AR-100",
          customer_id: accountId,
          invoice_date: "2026-07-31",
          due_date: "2026-08-31",
          currency: "EUR",
          lines: [
            {
              line_number: 1,
              description: "License",
              account: accountId,
              quantity: "2.5000",
              unit_price: "4.00",
              tax_amount: "0.25",
            },
          ],
        }}
        onSubmit={submit}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByLabelText("Customer UUID")).toHaveValue(accountId);
    expect(screen.getByText("EUR 10.25")).toBeInTheDocument();
    submitForm("Save invoice");
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({ customer_id: accountId }));
  });

  it("keeps payment AP and AR targets mutually exclusive and requires exactly one target", async () => {
    const user = userEvent.setup();
    const submit = vi.fn();

    render(<PaymentForm pending={false} onSubmit={submit} onCancel={vi.fn()} />);

    await user.clear(screen.getByLabelText("Amount"));
    await user.type(screen.getByLabelText("Amount"), "25.00");
    submitForm("Record payment");
    expect(await screen.findByText("Choose exactly one AP or AR invoice.")).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("AP invoice UUID"), apInvoiceId);
    expect(screen.getByLabelText("AR invoice UUID")).toHaveValue("");
    await user.type(screen.getByLabelText("AR invoice UUID"), arInvoiceId);
    expect(screen.getByLabelText("AP invoice UUID")).toHaveValue("");
    await user.selectOptions(screen.getByLabelText("Payment method"), "wire_transfer");
    await user.clear(screen.getByLabelText("Currency"));
    await user.type(screen.getByLabelText("Currency"), "eur");
    await user.type(screen.getByLabelText("Reference number"), "WIRE-1");
    await user.type(screen.getByLabelText("Description"), "Customer settlement");
    submitForm("Record payment");

    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        amount: "25.00",
        payment_method: "wire_transfer",
        currency: "EUR",
        ap_invoice: null,
        ar_invoice: arInvoiceId,
        reference_number: "WIRE-1",
        description: "Customer settlement",
      })
    );
  });
});
