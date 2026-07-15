"""Self-check for the escalation-parsing logic. Run: python test_orchestrator.py"""
import tempfile
from pathlib import Path

from task_graph import find_escalations, pending_escalations


def test_find_escalations():
    with tempfile.TemporaryDirectory() as tmp:
        ticket_dir = Path(tmp) / "T-001"
        ticket_dir.mkdir()

        assert find_escalations(ticket_dir) == []

        (ticket_dir / "notes.md").write_text(
            "## Implementation notes\nhandled the empty-list case\n"
            "ESCALATE: acceptance criteria conflict with spec\n"
            "just a regular note\n"
        )
        assert find_escalations(ticket_dir) == [
            "ESCALATE: acceptance criteria conflict with spec"
        ]


def test_pending_escalations():
    with tempfile.TemporaryDirectory() as tmp:
        tickets_dir = Path(tmp)
        (tickets_dir / "T-001").mkdir()
        (tickets_dir / "T-001" / "notes.md").write_text("all clear\n")
        (tickets_dir / "T-002").mkdir()
        (tickets_dir / "T-002" / "notes.md").write_text("ESCALATE: blocked on T-001\n")

        result = pending_escalations(tickets_dir)
        assert result == {"T-002": ["ESCALATE: blocked on T-001"]}


if __name__ == "__main__":
    test_find_escalations()
    test_pending_escalations()
    print("ok")
