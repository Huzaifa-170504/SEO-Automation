import type { DemoAuditResult } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "http://localhost:8000";

async function parseError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? `Request failed with status ${response.status}.`;
  } catch {
    return `Request failed with status ${response.status}.`;
  }
}

export async function runAudit(websiteUrl: string): Promise<DemoAuditResult> {
  const response = await fetch(`${API_BASE}/api/v1/audits`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ website_url: websiteUrl, company: "" }),
  });
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as DemoAuditResult;
}

export async function downloadReport(result: DemoAuditResult): Promise<void> {
  if (!result.access_token) throw new Error("PDF downloads are available for live audits.");
  const response = await fetch(`${API_BASE}/api/v1/audits/${result.audit_id}/report`, {
    headers: { "X-Audit-Token": result.access_token },
  });
  if (!response.ok) throw new Error(await parseError(response));
  const href = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = `seo-audit-${result.audit_id}.pdf`;
  anchor.click();
  URL.revokeObjectURL(href);
}
