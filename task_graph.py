"""File-based task graph: tickets/<run-id>/<ticket-id>/spec.json + notes.md, no SDK dependency."""
import json
from pathlib import Path

ESCALATE_MARKER = "ESCALATE:"
USER_INPUT_MARKER = "ESCALATE: need user input:"  # only a human can answer these
# "no-release" = orchestrator decided devops doesn't apply (work never leaves the repo).
TERMINAL_STATUSES = {"verified", "released", "no-release"}
TERMINAL_WITH_DEVOPS = {"released", "no-release"}


def find_escalations(ticket_dir: Path) -> list[str]:
    """Open ESCALATE: lines in a ticket's notes.md. Resolved ones get rewritten to RESOLVED:."""
    notes = ticket_dir / "notes.md"
    if not notes.exists():
        return []
    return [
        line.strip()
        for line in notes.read_text().splitlines()
        if line.strip().startswith(ESCALATE_MARKER)
    ]


def pending_escalations(tickets_dir: Path) -> dict[str, list[str]]:
    """Escalations across all tickets, keyed by ticket ID. Empty dict = nothing needs you."""
    if not tickets_dir.exists():
        return {}
    result = {}
    for ticket_dir in tickets_dir.iterdir():
        if ticket_dir.is_dir():
            escalations = find_escalations(ticket_dir)
            if escalations:
                result[ticket_dir.name] = escalations
    return result


def _status(spec_path: Path):
    """A spec's status, or None if it's unreadable (agent mid-write, invalid JSON)."""
    try:
        spec = json.loads(spec_path.read_text())
    except (OSError, ValueError):
        return None
    return spec.get("status") if isinstance(spec, dict) else None


def all_tickets_terminal(tickets_dir: Path, terminal: set[str] = TERMINAL_STATUSES) -> bool:
    """True once every ticket has a terminal status. False if none exist yet."""
    specs = list(tickets_dir.glob("*/spec.json"))
    if not specs:
        return False
    return all(_status(p) in terminal for p in specs)


def next_action(tickets_dir: Path, terminal: set[str], last_escalations: dict) -> tuple[str, dict]:
    """What the run loop does after a turn: 'resolve', 'stuck', 'done', or 'continue'.

    An escalation gets one orchestrator turn to resolve; if the exact same set is
    still open after that turn, it needs a human ('stuck'). Questions for the user stop at once.
    """
    escalations = pending_escalations(tickets_dir)
    needs_user = any(line.startswith(USER_INPUT_MARKER) for lines in escalations.values() for line in lines)
    if needs_user:
        return "stuck", escalations
    if escalations:
        return ("stuck" if escalations == last_escalations else "resolve"), escalations
    if all_tickets_terminal(tickets_dir, terminal):
        return "done", {}
    return "continue", {}
