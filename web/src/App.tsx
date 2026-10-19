import { FormEvent, useState } from "react";
import { AuditResults } from "./AuditResults";
import { runAudit } from "./api";
import { sampleAudit } from "./sample";
import type { DemoAuditResult } from "./types";

const githubUrl = "https://github.com/Huzaifa-170504/SEO-Automation";

export default function App() {
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [result, setResult] = useState<DemoAuditResult>(sampleAudit);
  const [isSample, setIsSample] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submitAudit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsRunning(true);
    try {
      const audit = await runAudit(websiteUrl);
      setResult(audit);
      setIsSample(false);
      window.setTimeout(() => document.querySelector("#results")?.scrollIntoView({ behavior: "smooth" }), 50);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The audit could not be completed.");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="SEO Automation home"><span className="brand-mark">H</span><span>SEO / AUTOMATION</span></a>
        <nav aria-label="Primary navigation"><a href="#workflow">Workflow</a><a href="#results">Evidence</a><a href="#engineering">Engineering</a></nav>
        <a className="github-link" href={githubUrl} target="_blank" rel="noreferrer">View source <span>↗</span></a>
      </header>

      <main id="top">
        <section className="hero section-shell">
          <div className="hero-copy">
            <p className="eyebrow"><span className="status-dot" /> Live engineering portfolio</p>
            <h1>SEO analysis that shows its work.</h1>
            <p className="hero-lede">A production-minded automation system that crawls real websites, turns raw HTML signals into structured issues, routes work to specialist agents, and creates actionable reports.</p>
            <div className="hero-actions"><a className="button button-primary" href="#try-it">Run an audit</a><a className="text-link" href="#workflow">Explore the system <span>↓</span></a></div>
            <dl className="hero-facts">
              <div><dt>15</dt><dd>live demo page limit</dd></div>
              <div><dt>SSRF</dt><dd>public-network validation</dd></div>
              <div><dt>24h</dt><dd>result retention window</dd></div>
            </dl>
          </div>

          <div className="audit-console" id="try-it">
            <div className="console-bar"><span>LIVE_AUDIT</span><span className="console-state"><i /> READY</span></div>
            <div className="console-body">
              <p className="console-label">Target website</p>
              <form onSubmit={submitAudit}>
                <label className="url-field"><span aria-hidden="true">⌁</span><input required type="text" inputMode="url" autoComplete="url" placeholder="example.com" value={websiteUrl} onChange={(event) => setWebsiteUrl(event.target.value)} disabled={isRunning} aria-describedby="audit-help" /></label>
                <input className="honeypot" name="company" tabIndex={-1} autoComplete="off" aria-hidden="true" />
                <button className="button run-button" type="submit" disabled={isRunning}>{isRunning ? <><span className="spinner" /> Auditing…</> : <>Start live audit <span>→</span></>}</button>
              </form>
              <p id="audit-help" className="console-help">Public sites only · respects robots.txt · up to 15 pages</p>
              {error && <p className="form-error" role="alert">{error}</p>}
              <div className="console-log" aria-live="polite">
                <p><span>01</span> Resolve and validate public target</p>
                <p><span>02</span> Discover sitemap and internal links</p>
                <p><span>03</span> Extract technical and on-page signals</p>
                <p><span>04</span> Route findings and assemble report</p>
              </div>
            </div>
          </div>
        </section>

        <section className="workflow section-shell" id="workflow" aria-labelledby="workflow-title">
          <div className="section-kicker"><span>01</span> System design</div>
          <div className="section-intro"><div><p className="eyebrow">A bounded agent workflow</p><h2 id="workflow-title">Automation where it helps. Determinism where it matters.</h2></div><p>The crawler and application code own facts, validation, persistence, and limits. AI supports strategy and drafting—never network safety or workflow truth.</p></div>
          <div className="architecture" role="img" aria-label="Browser to API, crawler, agents, Supabase, Gemini and PDF architecture">
            <div className="arch-node emphasis"><small>INTERFACE</small><strong>Recruiter web UI</strong><span>React · GitHub Pages</span></div><i>→</i>
            <div className="arch-node"><small>BOUNDARY</small><strong>Typed web API</strong><span>FastAPI · Vercel</span></div><i>→</i>
            <div className="arch-stack"><div className="arch-node"><small>EVIDENCE</small><strong>Website auditor</strong><span>HTTP · HTML · robots</span></div><div className="arch-node"><small>ROUTING</small><strong>Specialist agents</strong><span>Deterministic ownership</span></div></div><i>→</i>
            <div className="arch-stack"><div className="arch-node"><small>STATE</small><strong>Supabase</strong><span>Postgres · private files</span></div><div className="arch-node"><small>OUTPUT</small><strong>Readable reports</strong><span>JSON · PDF</span></div></div>
          </div>
          <div className="principles"><article><span>01</span><h3>Evidence first</h3><p>Every recommendation points back to an observed page, element, response, or crawl error.</p></article><article><span>02</span><h3>Safe by default</h3><p>Private networks, credentials in URLs, unsupported schemes, and unbounded public crawls are rejected.</p></article><article><span>03</span><h3>Human control</h3><p>Content workflows pause for review. Provider failure is explicit, bounded, and never presented as success.</p></article></div>
        </section>

        <AuditResults result={result} isSample={isSample} />

        <section className="engineering section-shell" id="engineering" aria-labelledby="engineering-title">
          <div className="section-kicker"><span>03</span> Under the hood</div>
          <div className="engineering-grid">
            <div><p className="eyebrow">Built beyond the happy path</p><h2 id="engineering-title">A demo architecture with production instincts.</h2><p className="lede">The project started as a Telegram automation workflow. The web layer reuses the same domain services while keeping hosting-specific behavior isolated.</p><a className="button button-secondary" href={githubUrl} target="_blank" rel="noreferrer">Read the code on GitHub ↗</a></div>
            <div className="decision-list">
              <article><span>01 / RELIABILITY</span><h3>Bounded work</h3><p>Fixed crawl limits, request timeouts, explicit failures, cancellation-aware local workflows, and short-lived public results.</p></article>
              <article><span>02 / SECURITY</span><h3>Server-owned trust</h3><p>Secrets remain backend-only. URL checks guard internal networks. Supabase tables use RLS with no anonymous data policies.</p></article>
              <article><span>03 / MAINTAINABILITY</span><h3>Ports, not rewrites</h3><p>The API, persistence adapter, crawler, report builder, Telegram interface, and frontend stay separate and testable.</p></article>
            </div>
          </div>
        </section>
      </main>

      <footer><div className="brand"><span className="brand-mark">H</span><span>SEO / AUTOMATION</span></div><p>Designed and engineered by Huzaifa · 2026</p><a href="#top">Back to top ↑</a></footer>
    </>
  );
}
