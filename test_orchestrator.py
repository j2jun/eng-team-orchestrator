"""Self-check for the escalation-parsing and config logic. Run: python test_orchestrator.py"""
import json
import tempfile
from pathlib import Path

from config import ROOT, house_rules_text, load_config, resolve_path, save_config, target_repo_path
from orchestrator import DispatchGate, _base_options, build_agents, build_orchestrator_prompt
from task_graph import (
    TERMINAL_WITH_DEVOPS, all_tickets_terminal, find_escalations, next_action, pending_escalations,
)


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



def test_malformed_spec_is_not_terminal():
    with tempfile.TemporaryDirectory() as tmp:
        t1 = Path(tmp) / "T-001"
        t1.mkdir()
        (t1 / "spec.json").write_text('{"status": "verif')  # agent mid-write
        assert all_tickets_terminal(Path(tmp)) is False
        (t1 / "spec.json").write_text('["not", "a", "dict"]')
        assert all_tickets_terminal(Path(tmp)) is False


def test_verified_is_not_terminal_when_devops_enabled():
    with tempfile.TemporaryDirectory() as tmp:
        t1 = Path(tmp) / "T-001"
        t1.mkdir()
        (t1 / "spec.json").write_text('{"status": "verified"}')
        assert all_tickets_terminal(Path(tmp), TERMINAL_WITH_DEVOPS) is False
        (t1 / "spec.json").write_text('{"status": "no-release"}')
        assert all_tickets_terminal(Path(tmp), TERMINAL_WITH_DEVOPS) is True


def test_next_action_gives_escalation_one_resolve_turn():
    with tempfile.TemporaryDirectory() as tmp:
        tickets_dir = Path(tmp)
        t1 = tickets_dir / "T-001"
        t1.mkdir()
        (t1 / "spec.json").write_text('{"status": "verified"}')
        terminal = {"verified"}
        assert next_action(tickets_dir, terminal, {}) == ("done", {})

        (t1 / "notes.md").write_text("ESCALATE: scope changed\n")
        action, esc = next_action(tickets_dir, terminal, {})
        assert action == "resolve" and esc == {"T-001": ["ESCALATE: scope changed"]}
        # same escalation still open after the resolve turn -> human needed
        assert next_action(tickets_dir, terminal, esc)[0] == "stuck"
        # orchestrator rewrote it -> no longer counted
        (t1 / "notes.md").write_text("RESOLVED: scope changed -> split into T-002\n")
        assert next_action(tickets_dir, terminal, esc) == ("done", {})
        # a question for the user stops immediately, no orchestrator turn spent on it
        (t1 / "notes.md").write_text("ESCALATE: need user input: which auth provider?\n")
        assert next_action(tickets_dir, terminal, {})[0] == "stuck"


def test_dispatch_gate_enforces_roster_concurrency_and_foreground():
    gate = DispatchGate({"swe", "qe"}, {"swe": 1})
    decision = lambda out: out["hookSpecificOutput"]["permissionDecision"]
    assert decision(gate.admit({"subagent_type": "general-purpose"}, "t0")) == "deny"
    first = gate.admit({"subagent_type": "swe", "prompt": "T-1", "run_in_background": True}, "t1")
    assert decision(first) == "allow"
    assert first["hookSpecificOutput"]["updatedInput"]["run_in_background"] is False
    assert first["hookSpecificOutput"]["updatedInput"]["prompt"] == "T-1"
    assert decision(gate.admit({"subagent_type": "swe"}, "t2")) == "deny"  # limit 1
    assert decision(gate.admit({"subagent_type": "qe"}, "t3")) == "allow"  # no limit set
    # orchestrator (no agent_id) can't implement; a subagent can
    assert decision(gate.check({"tool_name": "Bash", "tool_input": {}, "tool_use_id": "b1"})) == "deny"
    assert gate.check({"tool_name": "Bash", "tool_input": {}, "tool_use_id": "b2", "agent_id": "a1"}) == {}
    assert gate.check({"tool_name": "Read", "tool_input": {}, "tool_use_id": "r1"}) == {}
    gate.release("t1")
    assert decision(gate.admit({"subagent_type": "swe"}, "t4")) == "allow"


def test_base_options_restrict_tools_and_never_bypass():
    opts = _base_options({"max_budget_usd": 5}, "/repo", ["Read"], ["Bash"])
    assert opts["tools"] == ["Read"] and opts["allowed_tools"] == ["Bash", "Read"]
    assert opts["permission_mode"] == "dontAsk" and opts["max_budget_usd"] == 5
    assert opts["sandbox"]["allowUnsandboxedCommands"] is False
    assert opts["setting_sources"] == [] and opts["strict_mcp_config"] is True and opts["skills"] == []
    assert "sandbox" not in _base_options({"sandbox": False}, "/repo", ["Read"])


def test_paths_resolve_against_repo_not_cwd():
    assert resolve_path("x/rules.md") == ROOT / "x" / "rules.md"
    assert resolve_path("~/rules.md") == Path.home() / "rules.md"
    for bad in ({"target_repo": "."}, {"target_repo": None}, {"target_repo": "/no/such/dir"}):
        try:
            target_repo_path(bad)
            assert False, f"expected SystemExit for {bad}"
        except SystemExit:
            pass
    with tempfile.TemporaryDirectory() as tmp:
        assert target_repo_path({"target_repo": tmp}) == Path(tmp).resolve()
        rules = Path(tmp) / "rules.md"
        rules.write_text("be nice")
        assert house_rules_text({"house_rules": str(rules)}) == "be nice"
        try:
            house_rules_text({"house_rules": str(Path(tmp) / "missing.md")})
            assert False, "expected SystemExit for missing house_rules"
        except SystemExit:
            pass


def test_prompts_are_scoped_to_run_folder():
    agents = build_agents({"roles": {"swe": {"enabled": True, "model": "sonnet"}}}, "", "tickets/RUN1/")
    assert "tickets/RUN1/<TICKET-ID>/spec.json" in agents["swe"].prompt
    text = build_orchestrator_prompt({}, agents, "", "tickets/RUN1/")
    assert "tickets/RUN1/BRIEF.md" in text

if __name__ == "__main__":
    test_find_escalations()
    test_pending_escalations()
    test_all_tickets_terminal()
    test_load_config_rejects_unknown_role()
    test_load_config_missing_file()
    test_build_agents_skips_disabled_roles()
    test_build_orchestrator_prompt_lists_roster_and_skips_disabled()
    test_malformed_spec_is_not_terminal()
    test_verified_is_not_terminal_when_devops_enabled()
    test_next_action_gives_escalation_one_resolve_turn()
    test_paths_resolve_against_repo_not_cwd()
    test_prompts_are_scoped_to_run_folder()
    test_dispatch_gate_enforces_roster_concurrency_and_foreground()
    test_base_options_restrict_tools_and_never_bypass()
    print("ok")
