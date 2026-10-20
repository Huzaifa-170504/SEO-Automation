import type {
  DemoAuditResult,
  DemoContentRequest,
  DemoContentResult,
  HealthResponse,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "http://localhost:8000";

async function parseError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? `Request failed with status ${response.status}.`;
  } catch {
    return `Request failed with status ${response.status}.`;
  }
}

export async function runAudit(
  websiteUrl: string,
  signal?: AbortSignal,
): Promise<DemoAuditResult> {
  const response = await fetch(`${API_BASE}/api/v1/audits`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ website_url: websiteUrl, company: "" }),
    signal,
  });
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as DemoAuditResult;
}

export async function generateContent(
  payload: DemoContentRequest,
  signal?: AbortSignal,
): Promise<DemoContentResult> {
  const response = await fetch(`${API_BASE}/api/v1/content`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, company: "" }),
    signal,
  });
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as DemoContentResult;
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE}/api/health`);
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as HealthResponse;
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

export async function downloadContentReport(
  result: DemoContentResult,
): Promise<void> {
  if (!result.access_token) throw new Error("The content report token has expired.");
  const response = await fetch(`${API_BASE}/api/v1/content/${result.content_id}/report`, {
    headers: { "X-Content-Token": result.access_token },
  });
  if (!response.ok) throw new Error(await parseError(response));
  const href = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = `seo-content-${result.content_id}.pdf`;
  anchor.click();
  URL.revokeObjectURL(href);
}
