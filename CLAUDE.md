# HAM — Home Assistance Ministry

Web app for one church's Men's Ministry home-assistance projects.
**Source of truth:** `docs/HAM_PRD_V1.md`. Cite sections as `PRD §N`. If a request conflicts with the PRD, say so before doing anything.

## Priorities (in order when they conflict)
1. Safety, legal licensing, and privacy are never traded for convenience (PRD §3.4, §3.5, §27.1, §68).
2. Humans decide; AI/automation only suggest or draft. Flow: AI suggestion → user accepts → HAM validates permissions/rules → transaction → audit event (PRD §3.2, §79).
3. Every consequential action records actor + UTC timestamp and emits an audit event (PRD §3.3, §58, §70.6).
4. Keep it simple — leaders and volunteers are unpaid. Minimize fields/clicks; prefer templates, reuse, prefill, and automation of deterministic rules (PRD §3.1, §76).

## Scope
- Build only V1 scope (PRD §73). Respect non-goals (PRD §75).
- Deferred — do NOT build, but keep a clean seam (interface + domain event): Google Drive (§50), Fitness & Accountability + SMS (§36), background checks (§44 — no status field in V1), multilingual, multi-campus (§74).
- HAM must keep working if any integration is down (§70.3).

## Engineering defaults
- Relational DB; domain-oriented backend API; responsive PWA; background jobs for reminders, retention, waitlists, calendar sync (§78).
- Store timestamps in UTC; present in local time (§70.5).
- WCAG 2.2 AA where practical (§70.4). Core pages load in ~2s (§70.2).
- Least-privilege authorization enforced server-side on every endpoint (§67, §68).
- Never put requester name, address, or circumstances in Google Calendar, public/member dashboards, aggregate reports, logs, or AI prompts that don't need them (§51.1, §63, §68).
- Fixed business rules (reliability weights, staffing timelines, retention periods, link lifetimes, upload limits) live in ONE versioned rules module — never scattered literals, never admin-configurable (§34, §76).
- Comments: delete-only, never edit (§57). Incidents: immutable + amendments (§56). Agreements: exact version retained 7 years (§41, §42).

## Stack
TBD — record the decision as `docs/adr/0001-stack.md` (ham-architect drafts, product owner decides). Update this section once decided, including commands:
- Install: `TBD`
- Test: `TBD`
- Lint/typecheck: `TBD`
- Migrate DB: `TBD`

## PRD gaps
Never silently invent behavior the PRD leaves open. Log it in `docs/prd-open-questions.md` as `Q-NNN` with the PRD section, the options, and a proposed default; mark code that depends on it with `// PRD-GAP Q-NNN`.

## Agent team (`.claude/agents/`)
| Agent | Use for | Writes code? |
|---|---|---|
| ham-architect | Domain model, API/module design, ADRs, feature slicing | No (plans) |
| ham-ux-designer | Personas, journeys, screen flows, microcopy, usability reviews (`docs/ux/`) | No (design docs) |
| ham-ui-designer | Design system tokens/components, hi-fi screen specs, visual QA screenshots (`design-system/`) | Tokens/styles only |
| ham-backend-engineer | Entities, migrations, API endpoints, permissions, audit | Yes |
| ham-rules-engineer | State machines, staffing/waitlist timelines, reliability, retention jobs | Yes |
| ham-frontend-engineer | PWA screens, mobile flows, accessibility | Yes |
| ham-integrations-engineer | Google Calendar, domain events/outbox, adapters for deferred systems | Yes |
| ham-ai-engineer | Advisory AI service layer and guardrails | Yes |
| ham-test-engineer | Tests, PRD §77 acceptance scenario, running suites | Yes (tests only) |
| ham-privacy-security-reviewer | Access control, privacy leaks, audit coverage, MFA/impersonation | No (review) |
| ham-prd-guardian | PRD conformance, scope creep, gap detection | No (review) |

Default loop for a feature: architect + ux-designer (in parallel) → ui-designer → implementer(s) → test-engineer → ui-designer visual QA + ux-designer usability review + privacy-security-reviewer + prd-guardian → fix → commit.

## Design
- UX specs live in `docs/ux/`; the design system lives in `design-system/`. The frontend uses design tokens only, with no hard-coded colors or spacing.
- Mobile first (390px), then tablet (768px) and desktop (1280px+). Desktop layouts should make real use of the extra space rather than stretching the mobile layout.
- Dev server URL for visual QA: `TBD` (fill in once the stack is chosen).
