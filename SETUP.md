# HAM agent team — setup

## 1. Put the files in your HAM project folder
Unzip into the root of your HAM code folder (the one you open with Claude Code). You should end up with:

```
your-ham-folder/
├── CLAUDE.md                     ← project rules every agent reads
├── .claude/
│   ├── settings.json             ← blocks reading secrets, force-push, rm -rf
│   └── agents/                   ← the 11 agents
└── docs/
    ├── HAM_PRD_V1.md             ← COPY YOUR PRD HERE (not included in the zip)
    ├── prd-open-questions.md     ← decisions the PRD leaves open
    └── adr/                      ← architecture decision records
```

Then **restart Claude Code once** so it notices the new `.claude/agents/` folder.

## 2. First session: pick the stack
Ask Claude Code:

> Use the ham-architect agent to draft docs/adr/0001-stack.md. I'm not a professional developer and want low hosting cost and low maintenance. Explain the options in plain language.

Once you choose, have Claude fill in the "Stack" commands in `CLAUDE.md`.

## 3. Building a feature
Ask for a feature in plain words. Claude will usually pick the right agents; to be sure, name them:

> Build request intake (PRD §6–§7). Use ham-architect to plan it, then the engineers to build it, then ham-test-engineer, ham-privacy-security-reviewer, and ham-prd-guardian to check it.

You can also force a specific agent by typing `@` and picking it from the list.

## Setting the look and feel (do this early)
> Use ham-ux-designer to write the personas and the overall navigation for mobile and desktop. Then use ham-ui-designer to create the HAM design system and show me the home dashboard for a volunteer (mobile) and the HAM Director (desktop).

If the church has brand colors, a logo, or fonts, give them to ham-ui-designer at this step.

## Suggested build order
0. Personas, navigation, and design system (ham-ux-designer + ham-ui-designer)
1. Stack + skeleton, users/roles/permissions, audit log, MFA (§58–§60, §67)
2. Request intake, verification, media upload (§6, §7, §45)
3. Approval, rejection, reconsideration, urgent (§8, §10)
4. Site assessment, feasibility, scope, budget (§11–§14)
5. Tasks, templates, copy project (§15–§19)
6. Volunteer profiles, onboarding agreements, credentials (§20–§26, §42, §43)
7. Matching, invitations, waitlist, reconfirmation, reliability (§27–§34)
8. Calendar + notifications (§35, §51)
9. Project day: safety checklist, check-in, attendance, incidents (§37–§39, §56)
10. Completion, follow-up, survey, feedback, retention (§47, §53–§55)
11. AI assistant (§61, §65, §79)
12. Dashboards and reports (§63, §64, §72) → full §77 acceptance test

## About the agents
- Each one only sees what Claude hands it plus `CLAUDE.md`. It doesn't see your chat.
- Reviewers (privacy-security, prd-guardian) and the architect **cannot edit files**. That's deliberate.
- Agents with `memory: project` keep notes in `.claude/agent-memory/`. Commit that folder so the notes persist.
- To change an agent, edit its `.md` file. Changes are picked up within seconds.
