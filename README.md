# eng-team-orchestrator

A hybrid multi-agent orchestrator that models a small engineering team as Claude Agent SDK
subagents: TPM, Researcher, Tech Lead, SWE, QE, coordinated by a top-level orchestrator.

**Hybrid** = hierarchical dispatch (the orchestrator assigns tickets) + peer escalation
channels (subagents hand work to each other directly via shared files, only bubbling up to
the orchestrator when something needs a cross-workstream decision).

## How it's coordinated

No message bus — the task graph is plain files under `tickets/<TICKET-ID>/`:

- `spec.json` — ticket, title, acceptance_criteria, owner_module, open_questions, status
- `notes.md` — a running log every role reads/writes directly. Peer handoffs (SWE ↔ QE,
  SWE ↔ Researcher) happen here. Any line starting with `ESCALATE:` is a signal the
  orchestrator picks up on its next pass — everything else is between the agents.

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
how many tickets each role can run concurrently, the target repo this team operates on,
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

## Status

Routing is left to the top-level LLM's judgment per `agents/orchestrator.md` rather than
hand-coded in Python. Swap in deterministic Python routing if you need it to be less
judgment-based and more predictable.

Known limitation: subagent dispatch (the Task tool) runs asynchronously in this environment
— a single query/response cycle ends before a dispatched agent like tpm/swe/qe actually
finishes. `orchestrator.py`'s `run()` works around this with a bounded nudge-loop
(`max_turns` in config) that keeps checking the task graph until it reaches a terminal
state. This is a polling workaround, not an event-driven wait — fine for now, worth
revisiting if the SDK exposes a proper completion hook.
