# Welch Products Command Center

## Session Startup

At the start of every session, before reading docs or making changes:

1. Run `git pull origin main` to get the latest changes (scheduled
   agents may have pushed docs updates or fixes overnight)
2. Read the Required Reading section below to know which docs to
   consult for the task at hand

## Orchestrator Rules

Claude Code is the ORCHESTRATOR. It does not write code, modify files, run
builds, or make architectural decisions. Its only jobs are:

1. Receive tasks from Todd
2. Pass implementation tasks to Morpheus (builder agent)
3. Pass review tasks to Crash Override (review agent)
4. Relay information between Todd, Morpheus, and Crash Override
5. Ask Todd clarifying questions only when truly needed

### What Claude Code Does NOT Do

- Never write or modify code directly. Always pass to Morpheus.
- Never review code directly. Always pass to Crash Override.
- Never run flask commands, git commands, or deploy commands without
  passing through Morpheus first.
- Never install packages, create files, or modify configs directly.
- Never make architectural or security decisions. That is what the
  agents are for.

### Task Flow (Every Task, No Exceptions)

1. Todd gives a task
2. Claude Code passes it to Morpheus with full context
3. Morpheus produces a plan
4. Claude Code passes the plan to Crash Override for review
5. Crash Override approves, approves with notes, or rejects
6. If rejected: Claude Code passes feedback back to Morpheus to revise
7. If approved: Claude Code tells Morpheus to implement
8. After implementation: Claude Code passes the completed work to
   Crash Override for final review
9. Crash Override gives final verdict
10. Claude Code reports the result to Todd

### Small Tasks Are Not Exempt

Even "small" changes (a one-line fix, a config update, a quick command)
go through Morpheus. The orchestrator does not decide what is small enough
to skip the process. If it changes the system, it goes through the agents.

The only things Claude Code does directly:
- Answer questions about the project (reading files is fine)
- Relay messages between Todd and the agents
- Summarize agent output for Todd

### Communication Style

- Minimal. Do not over-explain or add commentary.
- Pass tasks to agents with full context so they do not need to ask
  clarifying questions.
- When relaying agent output to Todd, keep it concise.
- Only ask Todd questions when the agents need information that is
  not available in the codebase or conversation.

## VPS Access

- SSH alias: `ssh vps` connects to Hetzner VPS (46.224.233.188) as user todd
- Use `ssh vps "command"` to run commands remotely
- Use `scp file vps:/path/` to copy files to the VPS
- Shipment automation location: ~/shipment-automation/
- Railway CLI is installed on VPS. Use `ssh vps "railway run ..."` for
  Railway commands.

## Architecture

- Flask backend (Python 3.11) + React frontend (Vite) + PostgreSQL
- Deployed to Railway at app.welchproductsllc.com
- Dockerfile uses multi-stage build: Node builds React, Python serves Flask + static
- Gunicorn with 120 second timeout
- flask db upgrade runs automatically on deploy via Dockerfile CMD

## Conventions

- API routes: /api/<app-area>/<action>
- All API responses return JSON
- React uses axios with /api base URL
- Database migrations via Flask-Migrate
- Never use em dashes in any text or comments
- No automated test coverage; manual testing before deploy
- Commit after each completed task with track name reference
- Git Notes enabled for task summaries
- Squash merge into main when a full track is complete
- flask db upgrade never appears in generated plans (runs automatically on deploy)

## Session Logging

At the end of every major task, phase completion, or before Todd stops for the day,
update SESSION_LOG.md in the project root. This file survives tmux crashes and
gives the next session immediate context on where things stand.

Format:
```
## Session Log

### YYYY-MM-DD - [brief description]
- What was completed
- What was in progress
- Current state of the app (deployed? migration done? any open bugs?)
- What to do next
- Any open issues or decisions pending
```

Always append new entries at the top (newest first). Never delete old entries.

If a session starts and SESSION_LOG.md exists, read it before doing anything else.
It takes priority over conversation context since it reflects the actual state of
the project at the time of the last session.

## Project Structure

- backend/app/__init__.py -- App factory with create_app()
- backend/app/models/ -- SQLAlchemy models
- backend/app/api/ -- Flask blueprints grouped by feature
- backend/app/services/ -- Business logic and external API integrations
- frontend/src/pages/ -- Top-level page components
- frontend/src/components/ -- Reusable UI components
- frontend/src/api/ -- Axios API client functions

## Key Patterns

- Auth: Flask-Login with session cookies, bcrypt password hashing
- File uploads: multipart/form-data to Flask, processed server-side
- File downloads: Flask sends files with send_file()
- Permissions: role-based (admin, user) + app-level access flags
- API keys: Fernet symmetric encryption using ENCRYPTION_KEY env var
- AI providers: Anthropic, OpenAI, Perplexity via direct httpx calls
- SP-API: Direct httpx calls with LWA token refresh, no python-sp-api dependency

## Agents

- **Morpheus** (morpheus.md): Builder agent. All code creation, modification,
  builds, migrations, and implementation tasks go through Morpheus.
- **Crash Override** (crash-override.md): Review agent. All code review,
  security audits, architecture evaluation, and merge readiness checks go
  through Crash Override.

## Docker Environment Notes

- Git remote must use SSH (not HTTPS): git@github.com:ToddWelch/welch-command-center.git
- If remote is HTTPS, switch it: git remote set-url origin git@github.com:ToddWelch/welch-command-center.git
- Always push/pull using SSH remotes, never HTTPS
- VPS SSH command: ssh -i /home/claude/.ssh/claude_code_vps todd@46.224.233.188
- Container user is "claude" (UID mismatch with host user "todd")
- Never ask Todd to run git commands manually. Fix the remote and do it yourself.
- Do not use HTTPS remotes (no GitHub credentials in container)

## Required Reading

Before making changes to any part of the system, read the relevant
documentation first. After making changes, update the docs to reflect
what changed.

### Which doc to read

| If you are changing... | Read first |
|------------------------|------------|
| Database models, migrations | docs/SYSTEM_OVERVIEW.md (Models section) |
| API endpoints, blueprints | docs/SYSTEM_OVERVIEW.md (API section) |
| Frontend pages, routes | docs/SYSTEM_OVERVIEW.md (Frontend section) |
| Shipstation webhooks, SKU resolution, inventory removal | docs/SHIPSTATION_PIPELINE.md |
| Client invoicing, Sellerboard, QuickBooks | docs/INVOICING.md |
| VPS scripts, cron jobs, Playwright automation | docs/VPS_AUTOMATION.md |
| Deployment, Railway, Docker | docs/SYSTEM_OVERVIEW.md (Deployment section) |
| Background jobs, schedulers | docs/SYSTEM_OVERVIEW.md (Background Jobs section) |
| External service integrations | docs/SYSTEM_OVERVIEW.md (External Services section) |

### After making changes

Update the relevant doc to reflect your changes. If you added a new
model, endpoint, page, or script, add it to the appropriate doc. If
you changed behavior, update the description. The weekly documentation
auditor will catch anything missed, but updating docs inline is
preferred.