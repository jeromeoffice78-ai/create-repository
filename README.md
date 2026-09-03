# Agency Overlord

A self-contained AI-first advertising agency command center built around a 100-specialist operating model.

## What is implemented

- Executive agency dashboard and commercial KPIs
- 100 AI specialist roles across five divisions
- 15-stage orchestration pipeline: Research → Scale/Retain
- Client/brand workspaces and hard financial guardrails
- CRM / sales Kanban pipeline
- Campaign portfolio and campaign creation
- Creative studio and performance leaderboard
- Cross-channel media-buying view
- Analytics / attribution views
- Finance, subscription tiers, invoices and client profitability
- Seven mandatory QA gates
- Approval actions with audit trail
- Publishing queue, authorization preflight and safe execution gate
- Integration registry for Meta Ads, Google Ads, YouTube, TikTok Ads, LinkedIn Ads, Stripe, Google Drive, Calendar and GA4
- Automations registry
- Executive reporting templates
- Client portal
- FastAPI REST API + SQLite database
- Optional OpenAI Responses API multi-agent orchestration
- Docker deployment files

## Critical publishing behavior

The application deliberately **does not fake platform publication**. A publishing job can only become eligible after:

1. The client/account owner has authorized the relevant provider integration.
2. Strategic, Creative, Technical, Brand, Policy, Financial, and Publishing QA are all Approved.
3. The requested daily budget is inside the client's hard financial limits.
4. Destination URL and conversion tracking are present.
5. The global live-publish switch is enabled.
6. A production provider adapter returns a confirmed external campaign/ad ID.

This is the correct implementation of full publishing rights: powerful permissions on explicitly authorized accounts, not bypassed platform security.

## Run immediately

```bash
python -m pip install -r requirements.txt
cp .env.example .env
./run.sh
```

Open: `http://localhost:8000`

## Stack

- FastAPI
- SQLite
- Vanilla responsive SPA
- Optional OpenAI Responses API
