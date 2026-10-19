import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("portfolio application", () => {
  it("presents the live audit and evidence-led sample", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "SEO analysis that shows its work." })).toBeTruthy();
    expect(screen.getByRole("button", { name: /start live audit/i })).toBeTruthy();
    expect(screen.getByText("Page has a noindex robots directive")).toBeTruthy();
  });
});
