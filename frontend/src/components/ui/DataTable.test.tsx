import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "./DataTable";

interface Row {
  id: string;
  name: string;
  status: string;
  amount: number;
}

const rows: Row[] = Array.from({ length: 12 }, (_, index) => ({
  id: `row-${index + 1}`,
  name: `Account ${String(index + 1).padStart(2, "0")}`,
  status: index % 2 === 0 ? "Active" : "Paused",
  amount: index + 1,
}));

const columns: ColumnDef<Row>[] = [
  {
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => row.original.name,
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => row.original.status,
  },
  {
    accessorKey: "amount",
    header: "Amount",
    cell: ({ row }) => row.original.amount,
  },
];

describe("DataTable", () => {
  it("filters, sorts, paginates, toggles columns, and invokes bulk actions with selected originals", async () => {
    const user = userEvent.setup();
    const archive = vi.fn<(selected: Row[]) => void>();

    render(
      <DataTable
        data={rows}
        columns={columns}
        searchKey="name"
        searchPlaceholder="Search accounts"
        enableRowSelection
        enableColumnVisibility
        bulkActions={[{ label: "Archive", onClick: archive, variant: "danger" }]}
        getRowId={(row) => row.id}
      />
    );

    expect(screen.getByText("Showing 1 to 10 of 12 results")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.getByText("Account 01")).toBeInTheDocument();
    expect(screen.queryByText("Account 12")).not.toBeInTheDocument();

    const iconButtons = screen.getAllByRole("button");
    const nextPageButton = iconButtons[2];
    if (!nextPageButton) throw new Error("Expected next page button");
    await user.click(nextPageButton);
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    expect(screen.getByText("Account 12")).toBeInTheDocument();

    const firstPageButton = iconButtons[0];
    if (!firstPageButton) throw new Error("Expected first page button");
    await user.click(firstPageButton);
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();

    const nameHeader = screen.getByRole("columnheader", { name: /Name/ });
    await user.click(nameHeader);
    await user.click(nameHeader);
    const bodyRows = screen.getAllByRole("row").slice(1);
    const firstBodyRow = bodyRows[0];
    if (!firstBodyRow) throw new Error("Expected at least one body row");
    expect(within(firstBodyRow).getByText("Account 12")).toBeInTheDocument();

    await user.clear(screen.getByPlaceholderText("Search accounts"));
    await user.type(screen.getByPlaceholderText("Search accounts"), "Account 03");
    expect(screen.getByText("Account 03")).toBeInTheDocument();
    expect(screen.queryByText("Account 12")).not.toBeInTheDocument();

    await user.clear(screen.getByPlaceholderText("Search accounts"));
    await user.type(screen.getByPlaceholderText("Search accounts"), "missing");
    expect(screen.getByText("No data available")).toBeInTheDocument();

    await user.clear(screen.getByPlaceholderText("Search accounts"));
    await user.type(screen.getByPlaceholderText("Search accounts"), "Account 01");
    await user.click(screen.getByLabelText("Select row row-1"));
    expect(screen.getByText("1 item selected")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Archive" }));
    expect(archive).toHaveBeenCalledWith([rows[0]]);

    await user.click(screen.getByRole("button", { name: "Clear Selection" }));
    expect(screen.queryByText("1 item selected")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox"), "status");
    expect(screen.queryByText("Active")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox"), "all");
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("renders an empty unselectable table without optional controls", () => {
    render(<DataTable data={[]} columns={columns} />);

    expect(screen.getByText("No data available")).toBeInTheDocument();
    expect(screen.getByText("Showing 1 to 0 of 0 results")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Select all rows")).not.toBeInTheDocument();
  });
});
