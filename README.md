<div align="center">

# SEO Automation

**A live SEO audit and content automation portfolio with evidence-led reports.**

[![Open Live Demo](https://img.shields.io/badge/Open_Live_Demo-173f35?style=for-the-badge&logo=github)](https://huzaifa-170504.github.io/SEO-Automation/)
[![CI](https://img.shields.io/github/actions/workflow/status/Huzaifa-170504/SEO-Automation/ci.yml?branch=main&style=for-the-badge&label=CI)](https://github.com/Huzaifa-170504/SEO-Automation/actions/workflows/ci.yml)

[Live demo](https://huzaifa-170504.github.io/SEO-Automation/) · [Architecture](#live-architecture) · [Run locally](#local-development) · [Security](#security-model)

</div>

The platform crawls websites, detects technical and on-page issues, routes findings to specialist agents, researches competitor pages, creates reviewed SEO content, and produces downloadable reports. The recruiter web interface reuses the same core workflow as the Telegram bot instead of duplicating business logic.

> **Recruiter quick start:** Open the [live demo](https://huzaifa-170504.github.io/SEO-Automation/), run a public website audit, then open **Content** to provide a primary keyword, secondary keywords, and up to two competitor URLs. Both the audit and the final content workflow can be downloaded as PDF reports. Public audits are limited to the first 15 discovered pages.

## Live architecture

```text
Recruiter
  -> React + TypeScript UI on GitHub Pages
  -> FastAPI on Vercel
  -> Website auditor, competitor research, writer, and reviewer
  -> Supabase Postgres + private PDF Storage
  -> Gemini content generation
```

The public demo is intentionally bounded to 15 pages and 180 seconds. The existing Telegram workflow retains its configurable full-site behavior.

## What the project demonstrates

- Whole-site discovery through internal links, robots.txt, and sitemaps
- Public-network URL validation and redirect checks against SSRF targets
- Structured SEO findings with severity, evidence, affected URL, and recommendation
- Deterministic routing to website-auditor, content-strategist, and content-writer agents
- Keyword-led competitor research using up to two public URLs
- Strategy, drafting, deterministic review, and one bounded automatic revision
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

Without Supabase variables, the web API uses process-local memory for development. Configure `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and `RATE_LIMIT_SALT` together for durable persistence. Content generation also requires `GEMINI_API_KEY`. Never expose either secret in the frontend.

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

1. Confirm both migrations under `supabase/migrations/` are present in the intended Supabase project.
2. Add the backend environment variables from `.env.example` to Vercel, including `SUPABASE_SECRET_KEY` and `GEMINI_API_KEY`.
3. Deploy the repository as a Vercel FastAPI project using `main.py`.
4. Confirm `VITE_API_BASE_URL` in the Pages workflow points to the stable Vercel production alias.
5. Run the `Deploy recruiter demo` workflow; it enables GitHub Pages with **GitHub Actions** as its source.
6. Verify `/api/health`, one live 15-page audit, audit PDF download, one competitor-backed content job, and content PDF download.

The migration, Vercel deployment, GitHub Pages publication, and external credentials must be verified independently; local tests do not prove those external steps succeeded.

## Security model

- The browser receives no Supabase or Gemini secret.
- Result retrieval requires a high-entropy token; only its SHA-256 hash is stored.
- Content jobs require the opaque token of a completed live audit and receive their own separate result token.
- Supabase demo tables have RLS enabled and grant no anonymous or authenticated-user access.
- PDFs are stored in a private bucket and are streamed through the API after token validation.
- Client identifiers are salted and hashed before rate-limit persistence.
- Audit targets must use HTTP(S), contain no credentials, and resolve only to public addresses.

## License

MIT
