"""Loads/saves team.config.json — the persisted, user-editable team setup."""
import json
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
CONFIG_PATH = ROOT / "team.config.json"
VALID_ROLES = {"pm", "tpm", "researcher", "tech-lead", "swe", "qe", "devops"}
OPTIONAL_ROLES = ["pm", "devops"]  # opt-in: pm needs open-ended requests, devops needs a deploy target

DEFAULTS = {
    "target_repo": None,
    "house_rules": None,
    "max_turns": 20,
    "concurrency": {"swe": 4, "qe": 3, "researcher": 2, "tpm": 2},
    "roles": {role: {"enabled": role not in OPTIONAL_ROLES, "model": "sonnet"} for role in VALID_ROLES},
}


def load_config(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        raise SystemExit(f"No {path.name} found — run `python setup.py` first.")
    config = json.loads(path.read_text())
    unknown = set(config.get("roles", {})) - VALID_ROLES
    if unknown:
        raise SystemExit(f"Unknown role(s) in {path.name}: {sorted(unknown)}. Valid: {sorted(VALID_ROLES)}")
    return config


def save_config(config: dict, path: Path = CONFIG_PATH) -> None:
    path.write_text(json.dumps(config, indent=2) + "\n")


def resolve_path(value: str, base: Path = ROOT) -> Path:
    """Expand ~; relative paths resolve against `base` (where team.config.json lives), not the CWD."""
    p = Path(value).expanduser()
    return (p if p.is_absolute() else base / p).resolve()


def target_repo_path(config: dict) -> Path:
    """The repo agents operate on. Refuses this orchestrator's own repo — agents run with
    bypassPermissions and would edit the orchestrator itself."""
    value = config.get("target_repo")
    if not value:
        raise SystemExit("No target_repo in team.config.json — run `python setup.py`.")
    path = resolve_path(value)
    if not path.is_dir():
        raise SystemExit(f"target_repo {path} is not a directory.")
    if path == ROOT:
        raise SystemExit(f"target_repo is this orchestrator's own repo ({ROOT}); point it at the repo the team should work on.")
    return path


def house_rules_text(config: dict) -> str:
    value = config.get("house_rules")
    if not value:
        return ""
    path = resolve_path(value)
    if not path.is_file():
        raise SystemExit(f"house_rules file not found: {path}")
    return path.read_text()
