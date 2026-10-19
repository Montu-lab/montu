# Agent Coordination — Montu sprint

This repo is the shared coordination surface for agents working on Montu.
Commit every message you leave here so the other side can see it.

## Who's who

- **Muse** — Jayme's personal agent. I own the repo locally (synced with
  `origin/main`), keep product direction, context docs, and the bigger
  picture. I check this file and the repo state regularly during sprints.
- **Codex** — sprint builder. Ships product code fast. You're welcome.

## How to reach me

1. **Leave a note here.** Append to the Inbox below, commit, and push.
   I will reply in this same file.
2. **Or open a GitHub issue** in JaymeKame/montu if it's a bug or a task
   you want tracked.
3. **Urgent:** ping Jayme and he'll relay in chat.

## Inbox

<!-- Newest entries at the top. Format: [YYYY-MM-DD HH:MM TZ — Author] message -->

- [2026-10-19 15:05 PDT — Muse] Hello, Codex. Sprint's on. Grab a workstream,
  announce it here, push branches often. I review and own merges. Good building.

## Working agreement

- Work on your own branch per workstream (`codex/<topic>`). Never push to
  `main` directly. Never force-push.
- Announce what you're picking up in the Inbox so we don't duplicate work.
- Commit + push at meaningful milestones; I can read your diffs and PRs.
- **Merges are Jayme's call.** Open a PR and I'll review it against product
  direction; Jayme gives the final nod.
- **Deploy target:** montu.app is the live domain, but as of 2026-10-19 it
  serves a placeholder marketing template, NOT this product. Getting this
  repo live at montu.app (Vercel project wiring + domain) is part of the
  sprint; Vercel wiring needs Jayme's login.
- Product orientation before you code: `README.md` (what's built),
  `docs/claude-code-context.md` (context for coding agents),
  `docs/sms-setup.md` (Twilio rail).
- Product principles that are non-negotiable: user-facing language is
  *play* (never scheduling or coordination as the promise); the promise
  "You matter. Come play." must be legible in every screen — if a screen
  feels like a calendar app, we've lost; no in-app voice chat (link out to
  their Discord); capture is one peak-dopamine action, never mandatory.
