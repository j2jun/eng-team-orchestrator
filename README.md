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
export ANTHROPIC_API_KEY=...
```

## Run

```bash
python orchestrator.py "add rate limiting to the /login endpoint"
```

## Self-check

```bash
python test_orchestrator.py
```

## Status

Architecture scaffold — routing is currently left to the top-level LLM's judgment per
`agents/orchestrator.md` rather than hand-coded in Python. Swap in deterministic Python
routing if you need it to be less judgment-based and more predictable.
