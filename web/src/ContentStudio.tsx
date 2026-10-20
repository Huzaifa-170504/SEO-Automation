import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { downloadContentReport, generateContent } from "./api";
import type { DemoAuditResult, DemoContentResult } from "./types";

interface ContentStudioProps {
  audit: DemoAuditResult | null;
  content: DemoContentResult | null;
  onContent: (content: DemoContentResult) => void;
  cancelSignal: number;
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

export function ContentStudio({ audit, content, onContent, cancelSignal }: ContentStudioProps) {
  const [primaryKeyword, setPrimaryKeyword] = useState("");
  const [secondaryKeywords, setSecondaryKeywords] = useState("");
  const [competitorUrls, setCompetitorUrls] = useState("");
  const [topic, setTopic] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestController = useRef<AbortController | null>(null);
  const headings = useMemo(
    () => strings(content?.strategy.recommended_headings ?? content?.strategy.headings),
    [content],
  );

  useEffect(() => {
    if (cancelSignal === 0) return;
    requestController.current?.abort();
    setIsRunning(false);
    setError("The current content request was cancelled in this browser.");
  }, [cancelSignal]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!audit?.access_token) {
      setError("Run a live website audit first. The sample result cannot authorize content generation.");
      return;
    }
    const secondary = secondaryKeywords.split(",").map((item) => item.trim()).filter(Boolean);
    const competitors = competitorUrls.split(/[,\n]/).map((item) => item.trim()).filter(Boolean);
    if (secondary.length < 1 || secondary.length > 8) {
      setError("Enter between 1 and 8 secondary keywords.");
      return;
    }
    if (competitors.length > 2) {
      setError("Enter no more than 2 competitor URLs.");
      return;
    }
    setError(null);
    setIsRunning(true);
    requestController.current = new AbortController();
    try {
      const generated = await generateContent({
        audit_id: audit.audit_id,
        audit_token: audit.access_token,
        primary_keyword: primaryKeyword,
        secondary_keywords: secondary,
        competitor_urls: competitors,
        topic: topic.trim() || undefined,
      }, requestController.current.signal);
      onContent(generated);
      window.setTimeout(
        () => document.querySelector("#content-result")?.scrollIntoView({ behavior: "smooth" }),
        50,
      );
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setError(caught instanceof Error ? caught.message : "Content generation failed.");
      }
    } finally {
      setIsRunning(false);
      requestController.current = null;
    }
  }

  return (
    <section className="content-studio section-shell" id="content" aria-labelledby="content-title">
      <div className="section-kicker"><span>03</span> Telegram workflow on the web</div>
      <div className="studio-grid">
        <div>
          <p className="eyebrow">Content strategy and creation</p>
          <h2 id="content-title">Turn audit evidence into a reviewed article.</h2>
          <p className="lede">The same internal workflow used by Telegram selects relevant audited pages, reads up to two competitor URLs, builds a strategy, drafts candidates, reviews them, and performs one bounded revision.</p>
          <div className="workflow-steps" aria-label="Content workflow steps">
            <span>Audit</span><i>→</i><span>Research</span><i>→</i><span>Strategy</span><i>→</i><span>Draft</span><i>→</i><span>Review</span>
          </div>
        </div>

        <form className="studio-form" onSubmit={submit}>
          <div className="audit-context">
            <span>ACTIVE AUDIT</span>
            <strong>{audit && !audit.access_token ? "Sample evidence only" : audit?.website_url ?? "No live audit yet"}</strong>
          </div>
          <label>Primary keyword<input required minLength={2} maxLength={200} value={primaryKeyword} onChange={(event) => setPrimaryKeyword(event.target.value)} placeholder="technical SEO automation" /></label>
          <label>Secondary keywords <small>comma separated, 1–8</small><input required value={secondaryKeywords} onChange={(event) => setSecondaryKeywords(event.target.value)} placeholder="website audit, SEO report, content workflow" /></label>
          <label>Competitor URLs <small>comma or line separated, maximum 2</small><textarea rows={3} value={competitorUrls} onChange={(event) => setCompetitorUrls(event.target.value)} placeholder="https://competitor.example/guide" /></label>
          <label>Topic <small>optional; defaults to primary keyword</small><input maxLength={300} value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="A practical guide to automated SEO audits" /></label>
          <button className="button button-primary" type="submit" disabled={isRunning || !audit?.access_token}>{isRunning ? <><span className="spinner" /> Running research and review…</> : <>Generate reviewed content <span>→</span></>}</button>
          {!audit?.access_token && <p className="form-note">Complete a live audit from the Audit menu to unlock this workflow.</p>}
          {error && <p className="form-error" role="alert">{error}</p>}
        </form>
      </div>

      {content && <article className="content-result" id="content-result">
        <header>
          <div><p className="eyebrow">Generated result</p><h3>{String(content.article.title ?? content.topic)}</h3></div>
          <span className={`content-status ${content.status}`}>{content.status.replaceAll("_", " ")}</span>
        </header>
        <div className="content-meta">
          <span>Primary: <strong>{content.primary_keyword}</strong></span>
          <span>Competitors read: <strong>{content.competitor_urls.length}</strong></span>
          <span>Revisions: <strong>{content.revisions_used}</strong></span>
          <span>Review score: <strong>{String(content.review.overall_score ?? "n/a")}</strong></span>
        </div>
        {headings.length > 0 && <div className="strategy-outline"><span>Recommended outline</span><ol>{headings.map((heading) => <li key={heading}>{heading}</li>)}</ol></div>}
        <div className="article-preview">{String(content.article.body ?? "The writer returned no article body.")}</div>
        <div className="result-actions">
          <button className="button button-primary" type="button" onClick={() => void downloadContentReport(content)}>Download content PDF</button>
          <span>Includes research, strategy, article, and review evidence.</span>
        </div>
      </article>}
    </section>
  );
}
