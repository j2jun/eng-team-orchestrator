"""Loads/saves team.config.json — the persisted, user-editable team setup."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "team.config.json"
VALID_ROLES = {"pm", "tpm", "researcher", "tech-lead", "swe", "qe", "devops"}
OPTIONAL_ROLES = ["pm", "devops"]  # opt-in: pm needs open-ended requests, devops needs a deploy target

DEFAULTS = {
    "target_repo": ".",
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
