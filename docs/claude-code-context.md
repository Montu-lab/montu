# Montu — context for Claude Code

You are being looped in as a sounding board on product and as the authority on
Jayme's deploy setup. This file is the full context of a long conversation
between Jayme Kame (repeat founder, SF) and his AI assistant, plus the state of
the repo. Read this, then help with the two jobs at the bottom.

## What Montu is

Montu is AI that gets humans to play together. V1 experiment: gaming sessions
("game nights"). A creator makes a game night (game, time, squad size, vibe) and
gets a shareable link. Fans tap the link, join with name + phone (no app, no
account). The session page becomes the pre-game lobby: live countdown, squad
grid, and the creator's join info (lobby code, party invite link, voice chat
link). Everyone goes and plays the actual game (CoD, Valorant, etc.). After,
each person taps "I played" and the record accrues.

Montu never touches the game itself. It owns everything AROUND the game: the
who, the when, the belonging before, the memory after.

**The promise (the whole product must feel like this):** in a world that tries
to tell you you are nothing, we believe you matter — you belong to the human
family, and you deserve to feel it. AI is used to make that happen exceptionally
well. IMPORTANT: this is never stated outright on the landing page. It must be
*inferred* from the product's position between AI and human relevance. Preaching
it kills it.

**What it is not:** a commitment network (that framing was explicitly killed),
a scheduling app with extra steps, an AI companion, a voice-chat competitor
(we do not build voice; it's a link field for their Discord), or a feed.

## Positioning

- The category (name TBD, fun-first): AI-assembled shared play. The 10-year
  branch: the same assembler works for anything humans do together.
- V1 niche: gaming sessions. Gaming is where Jayme has traction and industry
  contacts; it's the entry experiment, not the whole product.
- Defensibility: not the matching feature (Discord could ship that). The
  cross-platform record of who played with whom, the creator economy on top,
  and speed.

## The role of AI (the frontier answer)

Vague human desire in, done deal out. "I want to play something Friday, I'm
decent, keep it chill" becomes a squad, a time, and a lobby with zero
back-and-forth. A scheduling app makes the user do the herding; the AI does the
herding. Every model generation understands vaguer intentions and matches on
deeper compatibility, so the product improves as models improve without
changing shape. The model is a substitutable input; the record graph is the
compounding asset no lab gets by shipping a better model.

## Cold-start rule (standing, non-negotiable)

The product must be useful to ONE person, not a network. The atomic unit of
value: one player, one existing night, 30 seconds, no app, no begging in
Discord. That works with exactly one host and one player in the world. If any
step only makes sense at a million users, that step is wrong. Every screen gets
re-checked against this.

## Mechanics

- **Single-user value:** join a night in 30 seconds; the AI/concierge does the
  awkward herding work (DMing strangers, filling no-shows) that nobody wants to
  do. Declare once; the system works while you live your life.
- **"I played" incentive:** the record. Tapping it earns better future squads,
  re-invites, and a visible history ("12 nights, 8 with the same crew") that
  becomes your gamer identity. Light in v1; the validation is whether assembly
  itself is the value.
- **Host incentive (no money to promise yet):** distribution. We bring them
  players they didn't have; every night grows their community. Plus
  founding-host status (permanent badge, first in line when paid nights turn
  on), streamable moments with fans, and knowledge of who their most engaged
  fans are. Product shows host stats: nights hosted, players brought together.
- **Why not the group chat:** group chats are where plans go to die. They can't
  find five strangers at your level, fill a no-show at 7:55pm, or balance vibe.
  Group chats manage existing friends; Montu manufactures squads. Different jobs.
- **Monetization (later):** creator-hosted paid sessions, platform takes
  10-15%. V1 monetizes nothing; it buys traction.

## Stack and architecture

- Next.js 14 + TypeScript + Tailwind, in this repo (`~/workspace/montu` on the
  assistant's machine; this file lives at `docs/claude-code-context.md`).
- Firebase: client SDK for web, firebase-admin for API routes. Project
  `inzone-f93e4` (shared with InZone for now).
- Firestore collections: `intentions` (generic squad requests), `nights`
  (creator game nights), `nights/{id}/rsvps`, `sessions`, `confirmations`,
  `creator_interests`.
- API routes: `POST /api/intentions`, `GET /api/intentions?status=open`,
  `POST /api/nights`, `GET /api/nights/[code]`,
  `POST /api/nights/[code]/rsvp` (idempotent per phone, 409 when full),
  `POST /api/sessions` (accepts intention-grouping or `{nightId, ...}`),
  `GET /api/sessions/[id]`, `POST /api/sessions/[id]/confirm` (idempotent;
  session flips to `done` when all confirm), `POST /api/sms/webhook`
  (parses YES/NO into confirmations).
- Pages: `/` (landing + intake, headline "You matter. Come play."),
  `/creator` (host pitch + "Create a game night" CTA), `/creator/nights/new`
  (night creation → share card with link + copy button), `/n/[code]` (public
  night page: game art, seat-fill progress, who's in, join form),
  `/session/[id]` (pre-game lobby: countdown, squad, join info, "I played"),
  `/admin?key=ADMIN_SECRET` (concierge: open intentions, nights + RSVPs,
  "Assemble squad").
- **SMS architecture (rail vs room):** traditional SMS via Twilio = the
  notification rail (minimal copy + lobby link; reaches every phone, zero
  install). The session web page = the room (no-install, tap-and-you're-in,
  the scooter model). iMessage app extensions = deferred (needs a native iOS
  app, Apple-only). See `docs/sms-setup.md`.
- **Game art:** night/lobby pages must show the game's key art big. Mapping
  lives in `lib/game-art.ts` (Steam CDN for known games, graceful fallback).
  If it's missing or ugly, that's a bug.
- Copy rule: belonging-first, fun-first. No duty/commitment/reliability
  language anywhere user-facing.

## Current state (2026-09-28)

- `npm run build` is green; pages smoke-tested at 200 locally.
- STUBBED (needs Jayme): Firestore writes (no `FIREBASE_SERVICE_ACCOUNT` in the
  build VM — routes return clean 503s without it), Twilio outbound (no creds),
  matching is concierge-assisted via `/admin` (no auto-matcher yet).
- Env vars needed: `FIREBASE_SERVICE_ACCOUNT`, `ADMIN_SECRET`,
  `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM` (+ the public Firebase client
  keys in `.env.local.example`).
- Creator reactivation: `creators/scripts/export-pending-creators.js` exports
  InZone's `influencers` where `status=='pending'` (creators who applied, never
  followed up). Outreach draft at `creators/reactivation-email-draft.md`
  (DRAFT — never send without Jayme's exact-text approval).
- Ad plan: `hexclave-campaign-plan.md`. NOTE: Hexclave is analytics +
  session-replay, NOT an ad network. Paid spend runs on TikTok/Meta Ads with
  Hexclave doing attribution. Jayme's TikTok campaign `tiktok_games_01` is
  live (9,076 arrivals / 7d as of 2026-09-29); pause-vs-keep is his call.
- InZone code was reused by copy (auth, Firebase patterns). Nothing in any
  InZone repo was modified; no InZone CI triggered. Keep it that way.

## Boundaries

- Never use or mention a $9M Ortis exit (false claim; never happened).
- No outreach sent without Jayme's exact-text approval. No ad spend changes
  without his approval.
- Build decisions: full autonomy. Anything user-facing that Jayme would need
  to recognize as his voice: check with him.

## Your two jobs

1. **Sounding board:** pressure-test the product thinking above. Jayme's
   sharpest critiques so far: the product must not read as a scheduling app;
   every screen must earn the belonging promise implicitly; single-user value
   is non-negotiable. Argue back where we're kidding ourselves.
2. **Deploy:** tell us EXACTLY what to do to get a Vercel preview deployment
   working with Jayme's current setup. He builds with Cursor/Codex/Claude
   Code, deploys on Vercel, and is creating a new GitHub repo for this product
   tonight. Give the concrete sequence: repo → Vercel project wiring (dashboard
   import vs `vercel` CLI), preview vs production env vars, anything his setup
   needs that a generic guide would miss. The assistant will execute what
   doesn't need Jayme's credentials; flag exactly which steps only he can do.

---
---

# Full conversation transcript

The verbatim transcript now lives in `docs/conversation-transcript.md`: all 47
messages of this side chat ("Explore AI cooperative play in InZone"), every word
exactly as stored, in chronological order (2026-09-28 to 2026-10-09).

Correction (2026-10-09): the transcript previously inlined here (2026-09-29
version) is removed. It contained one paraphrased, non-verbatim assistant message
and an unverified completeness claim. The replacement was regenerated from the
authoritative conversation store: event seq 22371 through 82233, user and
assistant messages only, empty tool-only turns and system notices omitted.
