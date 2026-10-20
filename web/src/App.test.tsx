import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

globalThis.fetch = async () =>
  new Response(
    JSON.stringify({
      status: "ok",
      service: "seo-automation-api",
      persistence: "supabase",
      demo_max_pages: 15,
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );

describe("portfolio application", () => {
  it("presents the live audit and evidence-led sample", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "SEO analysis that shows its work." })).toBeTruthy();
    expect(screen.getByRole("button", { name: /start live audit/i })).toBeTruthy();
    expect(screen.getByRole("link", { name: /create article/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /cancel request/i })).toBeTruthy();
    expect(screen.getByRole("heading", { name: /turn audit evidence/i })).toBeTruthy();
    expect(screen.getByText("Page has a noindex robots directive")).toBeTruthy();
  });
});
