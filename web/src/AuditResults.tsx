import { useMemo, useState } from "react";
import { downloadReport } from "./api";
import type { DemoAuditResult, Severity } from "./types";

const severities: Array<Severity | "all"> = ["all", "critical", "high", "medium", "low", "info"];

function label(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

interface Props {
  result: DemoAuditResult;
  isSample: boolean;
}

export function AuditResults({ result, isSample }: Props) {
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [expanded, setExpanded] = useState<string | null>(result.issues[0]?.issue_id ?? null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const issues = useMemo(
    () => result.issues.filter((issue) => severity === "all" || issue.severity === severity),
    [result.issues, severity],
  );

  async function handleDownload() {
    setDownloadError(null);
    try {
      await downloadReport(result);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "Unable to download the report.");
    }
  }

  return (
    <section className="results section-shell" id="results" aria-labelledby="results-title">
      <div className="section-kicker"><span>02</span> Evidence</div>
      <div className="results-heading">
        <div>
          <p className="eyebrow">{isSample ? "Guided sample" : "Live audit completed"}</p>
          <h2 id="results-title">A report you can inspect, not a score you have to trust.</h2>
          <p className="lede">Every finding includes the affected URL, severity, owning agent, and a concrete next action.</p>
        </div>
        {!isSample && (
          <button className="button button-secondary" type="button" onClick={handleDownload}>Download PDF</button>
        )}
      </div>
      {downloadError && <p className="form-error" role="alert">{downloadError}</p>}
      {result.warnings.map((warning) => <p className="notice" key={warning}>{warning}</p>)}
      <div className="metrics" aria-label="Audit summary">
        <article><strong>{result.summary.pages_crawled}</strong><span>pages crawled</span></article>
        <article><strong>{result.summary.issue_count}</strong><span>issues found</span></article>
        <article><strong>{result.summary.severity_counts.high ?? 0}</strong><span>high priority</span></article>
        <article><strong>{result.summary.pages_failed}</strong><span>crawl failures</span></article>
      </div>
      <div className="filter-row" aria-label="Filter issues by severity">
        {severities.map((item) => (
          <button key={item} type="button" className={severity === item ? "filter active" : "filter"} onClick={() => setSeverity(item)}>
            {label(item)} {item !== "all" && <span>{result.summary.severity_counts[item] ?? 0}</span>}
          </button>
        ))}
      </div>
      <div className="issue-list">
        {issues.length === 0 && <p className="empty-state">No issues match this filter.</p>}
        {issues.map((issue, index) => {
          const isOpen = expanded === issue.issue_id;
          return (
            <article className={`issue-card severity-${issue.severity}`} key={issue.issue_id}>
              <button type="button" className="issue-summary" aria-expanded={isOpen} onClick={() => setExpanded(isOpen ? null : issue.issue_id)}>
                <span className="issue-index">{String(index + 1).padStart(2, "0")}</span>
                <span className={`severity-pill ${issue.severity}`}>{issue.severity}</span>
                <span className="issue-title">{issue.title}</span>
                <span className="issue-toggle" aria-hidden="true">{isOpen ? "−" : "+"}</span>
              </button>
              {isOpen && (
                <div className="issue-detail">
                  <div><span>Affected page</span><a href={issue.url ?? undefined} target="_blank" rel="noreferrer">{issue.url ?? "Site-level finding"}</a></div>
                  <div><span>What was found</span><p>{issue.description}</p></div>
                  <div><span>Recommended action</span><p>{issue.recommendation ?? "Review the affected element."}</p></div>
                  <div className="agent-owner"><span>Assigned agent</span><code>{issue.assigned_agent ?? "website_auditor"}</code><small>{label(issue.category)}</small></div>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
