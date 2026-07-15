"""File-based task graph: tickets/<id>/spec.json + notes.md, no SDK dependency."""
from pathlib import Path

ESCALATE_MARKER = "ESCALATE:"


def find_escalations(ticket_dir: Path) -> list[str]:
    """Lines in a ticket's notes.md that need the orchestrator's attention."""
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
