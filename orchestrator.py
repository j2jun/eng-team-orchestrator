"""Hybrid multi-agent SWE team orchestrator, built on the Claude Agent SDK.

Hierarchical dispatch (this process assigns tickets to subagents) + peer escalation
channels (subagents hand off to each other via tickets/<id>/notes.md, only bubbling up
to this orchestrator on an ESCALATE: line). See agents/orchestrator.md for the routing
contract given to the top-level session.
"""
import asyncio
import sys
from pathlib import Path

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, ClaudeSDKClient

from task_graph import pending_escalations

ROOT = Path(__file__).parent
AGENTS_DIR = ROOT / "agents"


def _prompt(name: str) -> str:
    return (AGENTS_DIR / name).read_text()


AGENTS = {
    "pm": AgentDefinition(
        description="Turns open-ended requests into a product brief: goal, user value, success metric.",
        prompt=_prompt("pm.md"),
        tools=["Read", "Write", "Glob", "Grep"],
        model="sonnet",
    ),
    "tpm": AgentDefinition(
        description="Scopes requests into specs + non-overlapping ticket breakdowns.",
        prompt=_prompt("tpm.md"),
        tools=["Read", "Write", "Glob", "Grep"],
        model="sonnet",
    ),
    "researcher": AgentDefinition(
        description="Runs feasibility spikes on tickets with open_questions before implementation.",
        prompt=_prompt("researcher.md"),
        tools=["Read", "Write", "WebFetch", "WebSearch", "Bash"],
        model="sonnet",
    ),
    "tech-lead": AgentDefinition(
        description="Owns cross-ticket interface contracts and module-boundary coherence.",
        prompt=_prompt("tech_lead.md"),
        tools=["Read", "Write", "Grep", "Glob"],
        model="sonnet",
    ),
    "swe": AgentDefinition(
        description="Implements one ticket inside its assigned owner_module boundary.",
        prompt=_prompt("swe.md"),
        tools=["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
        model="sonnet",
    ),
    "qe": AgentDefinition(
        description="Writes test plans in parallel with SWE, then verifies diffs against them.",
        prompt=_prompt("qe.md"),
        tools=["Read", "Write", "Bash", "Grep", "Glob"],
        model="sonnet",
    ),
    "devops": AgentDefinition(
        description="Ships verified tickets: release strategy, rollback plan, post-release health.",
        prompt=_prompt("devops.md"),
        tools=["Read", "Write", "Bash", "Grep", "Glob"],
        model="sonnet",
    ),
}


async def run(request: str) -> None:
    options = ClaudeAgentOptions(
        agents=AGENTS,
        system_prompt=_prompt("orchestrator.md"),
        allowed_tools=["Task", "Read", "Write", "Glob", "Grep"],
        cwd=str(ROOT),
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query(f"New request: {request}")
        async for message in client.receive_response():
            print(message)

    unresolved = pending_escalations(ROOT / "tickets")
    if unresolved:
        print(f"\n[orchestrator] unresolved escalations: {unresolved}")


if __name__ == "__main__":
    request_text = " ".join(sys.argv[1:])
    if not request_text:
        sys.exit("usage: python orchestrator.py <request text>")
    asyncio.run(run(request_text))
