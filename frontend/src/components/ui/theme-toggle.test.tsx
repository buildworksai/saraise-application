import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "@/lib/theme-provider";
import { ThemeToggle } from "./theme-toggle";

describe("ThemeToggle", () => {
  it("uses the mounted ThemeProvider context and cycles all theme modes", async () => {
    const user = userEvent.setup();

    render(
      <ThemeProvider defaultTheme="system" storageKey="saraise-theme-test">
        <ThemeToggle />
      </ThemeProvider>
    );

    const toggle = screen.getByRole("button", {
      name: "Current theme: system. Click to cycle themes.",
    });

    await user.click(toggle);
    expect(
      screen.getByRole("button", {
        name: "Current theme: light. Click to cycle themes.",
      })
    ).toBeInTheDocument();

    await user.click(toggle);
    expect(
      screen.getByRole("button", {
        name: "Current theme: dark. Click to cycle themes.",
      })
    ).toBeInTheDocument();

    await user.click(toggle);
    expect(
      screen.getByRole("button", {
        name: "Current theme: system. Click to cycle themes.",
      })
    ).toBeInTheDocument();
  });
});
