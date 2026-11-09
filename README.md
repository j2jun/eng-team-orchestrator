# eng-team-orchestrator

A hybrid multi-agent orchestrator that models a small engineering team as Claude Agent SDK
subagents: TPM, Researcher, Tech Lead, SWE, QE, coordinated by a top-level orchestrator.

**Hybrid** = hierarchical dispatch (the orchestrator assigns tickets) + peer escalation
channels (subagents hand work to each other directly via shared files, only bubbling up to
the orchestrator when something needs a cross-workstream decision).

## How it's coordinated

No message bus — the task graph is plain files in the target repo under
`tickets/<RUN-ID>/<TICKET-ID>/` (one folder per run, so old tickets never affect a new run):

- `spec.json` — ticket, title, acceptance_criteria, owner_module, open_questions, status
- `notes.md` — a running log every role reads/writes directly. Peer handoffs (SWE ↔ QE,
  SWE ↔ Researcher) happen here. Any line starting with `ESCALATE:` gets one orchestrator
  turn to resolve (it rewrites the line to `RESOLVED: <decision>`); if it's still open after
  that, the run stops and prints it for a human.

A run ends when every ticket is `verified` (or `released` / `no-release` when devops is enabled).

## Roles

| Agent | Role prompt | Engages when |
|---|---|---|
| pm | `agents/pm.md` | Request is open-ended about *what/why* — skipped for already-scoped tickets |
| tpm | `agents/tpm.md` | Always (after pm, if pm ran) — turns intent into non-overlapping tickets |
| researcher | `agents/researcher.md` | A ticket's spec has `open_questions` |
| tech-lead | `agents/tech_lead.md` | Multiple tickets share an interface or boundaries risk colliding |
| swe | `agents/swe.md` | Ticket is unblocked (no open_questions) — implements inside owner_module |
| qe | `agents/qe.md` | Same time as swe, not after — drafts tests from the spec, verifies the diff |
| devops | `agents/devops.md` | Ticket status is "verified" — decides release strategy, ships, owns rollback |

Full routing/escalation contract given to the top-level session lives in
`agents/orchestrator.md`.

## Setup

```bash
pip install claude-agent-sdk
```

Uses the same authenticated `claude` CLI you're already logged into — no separate API key
needed.

Then configure your team once:

```bash
python setup.py
```

This writes `team.config.json` (gitignored — it's per-user/per-machine): which optional
roles are enabled (pm, devops — off by default; tech-lead defaults on), model per role,
how many tickets each role can run concurrently, the target repo this team operates on
(stored as an absolute path; it can't be this orchestrator repo itself),
an optional house-rules file appended to every role's prompt, and how many nudge-turns the
orchestrator gets before giving up. Re-run `setup.py` any time to reconfigure — it pre-fills
your current values.

## Run

```bash
python orchestrator.py "add rate limiting to the /login endpoint"
```

### Bypass routing — dispatch one role directly

If you already know which role should handle something, skip the tpm→researcher→swe/qe
routing algorithm entirely:

```bash
python orchestrator.py --agent swe "fix the off-by-one in the rate limiter window"
python orchestrator.py --agent qe "write a test plan for tickets/RATE-LIMIT-1"
```

This runs that one role directly against the request — no Task-tool subagent dispatch, so
no async-completion waiting either; it just does its own tool calls and returns.

## Self-check

```bash
python test_orchestrator.py
```

## Safety

- Each session gets only its role's tools (`tools=`), and runs in `dontAsk` mode: anything
  not pre-approved is denied rather than every permission check being bypassed.
- Bash runs in the OS sandbox by default (`sandbox: true`): writes are confined to the target
  repo and network access is blocked. Deploy commands from devops will usually need it off.
  Write/Edit tools aren't path-scoped — they can still write outside the target repo.
- Sessions are isolated from your personal Claude Code setup (`setting_sources=[]`, no MCP
  servers, no skills). Without this, your hooks, plugins and agent catalog ride along on every
  call — in testing that was ~1.2M tokens and ~$5 for a single orchestrator turn.
- The orchestrator session's model is `orchestrator_model` (default `sonnet`). Unset, the CLI
  picks its own default, which can be Opus.
- `max_budget_usd` (default $10) stops a run, but it's checked between API calls, so one
  expensive call can overshoot it.
- The OS sandbox still allows writes to temp directories (`$TMPDIR`, `/tmp`).
- The orchestrator session has every role's tools available (subagents can't use a tool the
  session lacks); a hook denies the orchestrator itself anything beyond Agent/Read/Write/Glob/Grep.
- Dispatch is gated in code by a hook, not just prompt text: only roles on this run's team,
  at most `concurrency[role]` in flight at once, always in the foreground.

## Questions for you

There's no live user in a session. PM/TPM write `ESCALATE: need user input: <question>` to
`tickets/<RUN-ID>/QUESTIONS/notes.md`; the run stops immediately and prints it. Answer by
re-running with a clarified request.

## Status

Routing is left to the top-level LLM's judgment per `agents/orchestrator.md` rather than
hand-coded in Python. Swap in deterministic Python routing if you need it to be less
judgment-based and more predictable.

Subagent dispatch blocks until the agent finishes; it only runs in the background if the
model asks for `run_in_background`, and the dispatch hook turns that off. The nudge loop
(`max_turns` in config) drives the routing contract from one step to the next and is a
safety net, not a wait on async agents.

Known limitation: parallel SWEs share one working tree. `owner_module` keeps them out of each
other's files, but only by prompt, and concurrent test runs can collide. Per-ticket git
worktrees would fix this; that needs a merge step the orchestrator doesn't have yet.
