<div align="center">

# SEO Automation

**Evidence-led website auditing with deterministic AI-agent routing and recruiter-ready reports.**

[![Open Live Demo](https://img.shields.io/badge/Open_Live_Demo-173f35?style=for-the-badge&logo=github)](https://huzaifa-170504.github.io/SEO-Automation/)
[![CI](https://img.shields.io/github/actions/workflow/status/Huzaifa-170504/SEO-Automation/ci.yml?branch=main&style=for-the-badge&label=CI)](https://github.com/Huzaifa-170504/SEO-Automation/actions/workflows/ci.yml)

[Live demo](https://huzaifa-170504.github.io/SEO-Automation/) · [Architecture](#live-architecture) · [Run locally](#local-development) · [Security](#security-model)

</div>

The platform crawls websites, detects technical and on-page issues, routes findings to specialist agents, and produces actionable reports. It supports the existing Telegram workflow and a recruiter-facing web demo without duplicating audit business logic.

> **Recruiter quick start:** Open the [live demo](https://huzaifa-170504.github.io/SEO-Automation/), enter a public website URL, and review the issue evidence, specialist routing, and downloadable PDF report. Public audits are limited to 15 pages.

## Live architecture

```text
Recruiter
  -> React + TypeScript UI on GitHub Pages
  -> FastAPI on Vercel
  -> Website auditor and deterministic agent routing
  -> Supabase Postgres + private PDF Storage
```

The public demo is intentionally bounded to 15 pages and 180 seconds. The existing Telegram workflow retains its configurable full-site behavior.

## What the project demonstrates

- Whole-site discovery through internal links, robots.txt, and sitemaps
- Public-network URL validation and redirect checks against SSRF targets
- Structured SEO findings with severity, evidence, affected URL, and recommendation
- Deterministic routing to website-auditor, content-strategist, and content-writer agents
- Persistent Telegram audit, report, content, review, cancellation, ownership, and retention workflows
- Gemini content generation with a bounded local Qwen fallback
- Short-lived recruiter demo results and private PDF reports in Supabase
- Typed FastAPI and React boundaries with automated tests

## Repository layout

```text
app/                  Core Python application and Telegram workflow
app/web/              Recruiter demo API, service, and persistence adapter
main.py               Vercel ASGI entrypoint
web/                   React/TypeScript GitHub Pages application
supabase/migrations/  Versioned database migrations
tests/                 Backend business and API tests
.github/workflows/    CI and GitHub Pages deployment
```

## Local development

### Backend

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000 --env-file .env
```

Without Supabase variables, the web API uses process-local memory for development. Configure `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and `RATE_LIMIT_SALT` together for durable persistence. Never expose `SUPABASE_SECRET_KEY` in the frontend.

Vercel sets its platform marker automatically, causing the API to reject startup unless durable Supabase configuration is present. This prevents an accidental production deployment from silently using process-local memory.

### Frontend

```powershell
Set-Location web
Copy-Item .env.example .env.local
npm.cmd install
npm.cmd run dev
```

Open `http://localhost:5173/SEO-Automation/`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.test-tmp\phase1 -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check app/web app/agents/website_auditor.py tests/test_web_api.py tests/test_web_settings.py tests/test_website_auditor_reliability.py main.py --no-cache
Set-Location web
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
```

## Deployment checklist

1. Confirm the migration under `supabase/migrations/` is present in the intended Supabase project.
2. Add the backend environment variables from `.env.example` to Vercel.
3. Deploy the repository as a Vercel FastAPI project using `main.py`.
4. Set the GitHub repository variable `VITE_API_BASE_URL` to the deployed Vercel origin.
5. Enable GitHub Pages with **GitHub Actions** as its source.
6. Run the `Deploy recruiter demo` workflow.
7. Verify `/api/health`, one live 15-page audit, protected result retrieval, and PDF download.

The migration, Vercel deployment, GitHub Pages publication, and external credentials must be verified independently; local tests do not prove those external steps succeeded.

## Security model

- The browser receives no Supabase or Gemini secret.
- Result retrieval requires a high-entropy token; only its SHA-256 hash is stored.
- Supabase demo tables have RLS enabled and grant no anonymous or authenticated-user access.
- PDFs are stored in a private bucket and are streamed through the API after token validation.
- Client identifiers are salted and hashed before rate-limit persistence.
- Audit targets must use HTTP(S), contain no credentials, and resolve only to public addresses.

## License

MIT
