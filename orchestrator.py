"""Hybrid multi-agent SWE team orchestrator, built on the Claude Agent SDK.

Hierarchical dispatch (this process assigns tickets to subagents) + peer escalation
channels (subagents hand off to each other via tickets/<id>/notes.md, only bubbling up
to this orchestrator on an ESCALATE: line). See agents/orchestrator.md for the routing
contract given to the top-level session.

Team composition (which roles run, their models, concurrency, target repo, house
rules) comes from team.config.json — run `python setup.py` once to create it.
"""
import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, ClaudeSDKClient

from config import house_rules_text, load_config, target_repo_path
from task_graph import TERMINAL_STATUSES, TERMINAL_WITH_DEVOPS, next_action

ROOT = Path(__file__).parent
AGENTS_DIR = ROOT / "agents"

ROLE_DESCRIPTIONS = {
    "pm": "Turns open-ended requests into a product brief: goal, user value, success metric.",
    "tpm": "Scopes requests into specs + non-overlapping ticket breakdowns.",
    "researcher": "Runs feasibility spikes on tickets with open_questions before implementation.",
    "tech-lead": "Owns cross-ticket interface contracts and module-boundary coherence.",
    "swe": "Implements one ticket inside its assigned owner_module boundary.",
    "qe": "Writes test plans in parallel with SWE, then verifies diffs against them.",
    "devops": "Ships verified tickets: release strategy, rollback plan, post-release health.",
}
ROLE_PROMPT_FILES = {
    "pm": "pm.md", "tpm": "tpm.md", "researcher": "researcher.md",
    "tech-lead": "tech_lead.md", "swe": "swe.md", "qe": "qe.md", "devops": "devops.md",
}
ROLE_TOOLS = {
    "pm": ["Read", "Write", "Glob", "Grep"],
    "tpm": ["Read", "Write", "Glob", "Grep"],
    "researcher": ["Read", "Write", "WebFetch", "WebSearch", "Bash"],
    "tech-lead": ["Read", "Write", "Grep", "Glob"],
    "swe": ["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
    "qe": ["Read", "Write", "Bash", "Grep", "Glob"],
    "devops": ["Read", "Write", "Bash", "Grep", "Glob"],
}


CONTINUE_PROMPT = (
    "Continue: check whether any dispatched agents finished and proceed "
    "to the next step in the routing contract."
)
RESOLVE_PROMPT = (
    "These ESCALATE: lines are open, keyed by ticket: {escalations}\n"
    "Make the call on each (rescope, resplit, reassign). Then rewrite that line in the "
    "ticket's notes.md so it starts with `RESOLVED:` followed by your decision, and "
    "continue the routing contract. If one genuinely needs a human, leave it as ESCALATE:."
)


def _scoped(text: str, tickets_rel: str) -> str:
    """Point a prompt's tickets/ paths at this run's own folder."""
    return text.replace("tickets/", tickets_rel)


def _role_prompt(role: str, house_rules: str, tickets_rel: str = "tickets/") -> str:
    prompt = _scoped((AGENTS_DIR / ROLE_PROMPT_FILES[role]).read_text(), tickets_rel)
    if house_rules:
        prompt += f"\n\n## House rules\n{house_rules}"
    return prompt


def build_agents(config: dict, house_rules: str, tickets_rel: str = "tickets/") -> dict:
    agents = {}
    for role, settings in config["roles"].items():
        if not settings.get("enabled", True):
            continue
        agents[role] = AgentDefinition(
            description=ROLE_DESCRIPTIONS[role],
            prompt=_role_prompt(role, house_rules, tickets_rel),
            tools=ROLE_TOOLS[role],
            model=settings.get("model", "sonnet"),
        )
    return agents


def build_orchestrator_prompt(config: dict, agents: dict, house_rules: str, tickets_rel: str = "tickets/") -> str:
    text = _scoped((AGENTS_DIR / "orchestrator.md").read_text(), tickets_rel)
    roster = ", ".join(sorted(agents)) or "none"
    concurrency = ", ".join(f"{k}={v}" for k, v in config.get("concurrency", {}).items())
    text += (
        f"\n\n## This run's team\nAvailable agents: {roster}. Do not dispatch or reference "
        f"any agent not in this list — treat a disabled role's step in the routing algorithm "
        f"as skipped. Concurrency budget (max tickets to dispatch to a role at once): {concurrency}."
    )
    if house_rules:
        text += f"\n\n## House rules\n{house_rules}"
    return text


async def run(request: str) -> None:
    config = load_config()
    house_rules = house_rules_text(config)
    target_repo = target_repo_path(config)
    max_turns = config.get("max_turns", 20)

    # Each run gets its own task graph, so old tickets/escalations can't end a new run
    # early and ticket IDs can't collide across runs.
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    tickets_rel = f"tickets/{run_id}/"
    tickets_dir = target_repo / "tickets" / run_id
    print(f"[orchestrator] task graph: {tickets_dir}")

    agents = build_agents(config, house_rules, tickets_rel)
    terminal = TERMINAL_WITH_DEVOPS if "devops" in agents else TERMINAL_STATUSES

    options = ClaudeAgentOptions(
        agents=agents,
        system_prompt=build_orchestrator_prompt(config, agents, house_rules, tickets_rel),
        allowed_tools=["Task", "Read", "Write", "Glob", "Grep"],
        cwd=str(target_repo),
        permission_mode="bypassPermissions",
    )
    action, escalations = "continue", {}
    async with ClaudeSDKClient(options=options) as client:
        prompt = f"New request: {request}"
        last_escalations: dict = {}
        # Subagent dispatch can finish after the top-level turn ends, so keep nudging
        # until the task graph is terminal or an escalation survives a resolve turn.
        # ponytail: polling loop, not an event-driven wait on task completion —
        # upgrade if the SDK exposes a proper "await dispatched agent" hook.
        for _ in range(max_turns + 1):  # first request + max_turns nudges
            await client.query(prompt)
            async for message in client.receive_response():
                print(message)
            action, escalations = next_action(tickets_dir, terminal, last_escalations)
            if action in ("done", "stuck"):
                break
            last_escalations = escalations
            prompt = RESOLVE_PROMPT.format(escalations=json.dumps(escalations)) if escalations else CONTINUE_PROMPT
        else:
            print(f"[orchestrator] hit max_turns={max_turns} without reaching a terminal state.")

    if escalations:
        print(f"\n[orchestrator] escalations need a human: {escalations}")


async def run_single_agent(role: str, request: str) -> None:
    """Bypass the routing algorithm entirely — you pick the role, you dispatch it directly.

    No Task-tool subagent dispatch here, so no async-completion polling is needed: this
    role's own tool calls (Read/Write/Bash/...) run synchronously within its one turn.
    """
    config = load_config()
    if role not in config["roles"] or not config["roles"][role].get("enabled", True):
        raise SystemExit(
            f"'{role}' isn't enabled in team.config.json. "
            f"Enabled roles: {sorted(r for r, s in config['roles'].items() if s.get('enabled', True))}"
        )
    house_rules = house_rules_text(config)
    target_repo = str(target_repo_path(config))

    options = ClaudeAgentOptions(
        system_prompt=_role_prompt(role, house_rules),
        allowed_tools=ROLE_TOOLS[role],
        cwd=target_repo,
        permission_mode="bypassPermissions",
        model=config["roles"][role].get("model", "sonnet"),
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query(request)
        async for message in client.receive_response():
            print(message)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid multi-agent SWE team orchestrator")
    parser.add_argument(
        "--agent",
        choices=sorted(ROLE_PROMPT_FILES),
        help="Skip the routing algorithm and dispatch this one role directly with the request",
    )
    parser.add_argument("request", nargs="+", help="The request text")
    args = parser.parse_args()
    request_text = " ".join(args.request)

    if args.agent:
        asyncio.run(run_single_agent(args.agent, request_text))
    else:
        asyncio.run(run(request_text))


if __name__ == "__main__":
    main()
