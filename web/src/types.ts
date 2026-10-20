export type Severity = "critical" | "high" | "medium" | "low" | "info";

export interface DemoIssue {
  issue_id: string;
  severity: Severity;
  category: string;
  issue_type: string;
  title: string;
  description: string;
  url: string | null;
  recommendation: string | null;
  assigned_agent: string | null;
  evidence: Record<string, unknown>;
}

export interface DemoPage {
  url: string;
  status_code: number | null;
  title: string;
  meta_description: string;
  h1_headings: string[];
  canonical: string | null;
  image_count: number;
  internal_link_count: number;
  external_link_count: number;
  word_count: number;
  language: string | null;
  issues: string[];
}

export interface DemoAuditResult {
  audit_id: string;
  access_token: string | null;
  website_url: string;
  status: "completed";
  created_at: string;
  expires_at: string;
  summary: {
    pages_discovered: number;
    pages_crawled: number;
    pages_failed: number;
    issue_count: number;
    crawl_limit_reached: boolean;
    severity_counts: Partial<Record<Severity, number>>;
  };
  issues: DemoIssue[];
  pages: DemoPage[];
  warnings: string[];
}

export interface DemoContentRequest {
  audit_id: string;
  audit_token: string;
  primary_keyword: string;
  secondary_keywords: string[];
  competitor_urls: string[];
  topic?: string;
}

export interface DemoContentResult {
  content_id: string;
  access_token: string | null;
  audit_id: string;
  website_url: string;
  primary_keyword: string;
  secondary_keywords: string[];
  competitor_urls: string[];
  topic: string;
  status: "approved" | "human_review_required";
  created_at: string;
  expires_at: string;
  research: Record<string, unknown>;
  strategy: Record<string, unknown>;
  article: Record<string, unknown>;
  review: Record<string, unknown>;
  revisions_used: number;
}

export interface HealthResponse {
  status: "ok";
  service: string;
  persistence: "memory" | "supabase";
  demo_max_pages: number;
}
