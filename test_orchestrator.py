"""Self-check for the escalation-parsing and config logic. Run: python test_orchestrator.py"""
import json
import tempfile
from pathlib import Path

from config import load_config, save_config
from orchestrator import build_agents, build_orchestrator_prompt
from task_graph import all_tickets_terminal, find_escalations, pending_escalations


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


def test_all_tickets_terminal():
    with tempfile.TemporaryDirectory() as tmp:
        tickets_dir = Path(tmp)
        assert all_tickets_terminal(tickets_dir) is False  # nothing created yet

        t1 = tickets_dir / "T-001"
        t1.mkdir()
        (t1 / "spec.json").write_text('{"status": "implementing"}')
        assert all_tickets_terminal(tickets_dir) is False

        (t1 / "spec.json").write_text('{"status": "verified"}')
        assert all_tickets_terminal(tickets_dir) is True

        t2 = tickets_dir / "T-002"
        t2.mkdir()
        (t2 / "spec.json").write_text('{"status": "scoped"}')
        assert all_tickets_terminal(tickets_dir) is False


def test_load_config_rejects_unknown_role():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "team.config.json"
        path.write_text(json.dumps({"roles": {"not-a-real-role": {"enabled": True}}}))
        try:
            load_config(path)
            assert False, "expected SystemExit for unknown role"
        except SystemExit as e:
            assert "not-a-real-role" in str(e)


def test_load_config_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "team.config.json"
        try:
            load_config(path)
            assert False, "expected SystemExit for missing config"
        except SystemExit as e:
            assert "setup.py" in str(e)


def test_build_agents_skips_disabled_roles():
    config = {
        "roles": {
            "swe": {"enabled": True, "model": "sonnet"},
            "devops": {"enabled": False, "model": "sonnet"},
        }
    }
    agents = build_agents(config, house_rules="")
    assert "swe" in agents
    assert "devops" not in agents


def test_build_orchestrator_prompt_lists_roster_and_skips_disabled():
    config = {"concurrency": {"swe": 4}}
    agents = build_agents(
        {"roles": {"swe": {"enabled": True, "model": "sonnet"}}}, house_rules=""
    )
    text = build_orchestrator_prompt(config, agents, house_rules="")
    assert "swe" in text
    assert "devops" not in text.split("## This run's team")[1].split("\n")[1]


if __name__ == "__main__":
    test_find_escalations()
    test_pending_escalations()
    test_all_tickets_terminal()
    test_load_config_rejects_unknown_role()
    test_load_config_missing_file()
    test_build_agents_skips_disabled_roles()
    test_build_orchestrator_prompt_lists_roster_and_skips_disabled()
    print("ok")
