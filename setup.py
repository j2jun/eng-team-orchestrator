"""Interactive setup wizard: writes team.config.json. Re-run any time to reconfigure —
it pre-fills every answer with your current setting, so editing is just enter-to-keep."""
from pathlib import Path

from config import CONFIG_PATH, DEFAULTS, OPTIONAL_ROLES, VALID_ROLES, load_config, save_config


def ask(prompt: str, default) -> str:
    answer = input(f"{prompt} [{default}]: ").strip()
    return answer or str(default)


def ask_yn(prompt: str, default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"
    answer = input(f"{prompt} [{suffix}]: ").strip().lower()
    return default if not answer else answer.startswith("y")


def _abs(path: str) -> str:
    return str(Path(path).expanduser().resolve())


def main() -> None:
    current = load_config(CONFIG_PATH) if CONFIG_PATH.exists() else DEFAULTS

    print("=== Engineering Team Orchestrator Setup ===")
    if CONFIG_PATH.exists():
        print(f"(editing existing {CONFIG_PATH.name} — press enter to keep a value)")

    house_rules_default = current.get("house_rules") or "none"
    house_rules_answer = ask(
        "Path to a house-rules file prepended to every role's prompt ('none' to skip)",
        house_rules_default,
    )
    target_repo_answer = ask("Repo this team operates on", current.get("target_repo") or Path.cwd())
    config = {
        # Stored absolute, so runs don't depend on the directory you launch from.
        "target_repo": _abs(target_repo_answer),
        "house_rules": None if house_rules_answer.strip().lower() == "none" else _abs(house_rules_answer),
        "max_turns": int(ask("Max orchestrator nudge-turns before giving up", current["max_turns"])),
        "max_budget_usd": float(ask("Max spend per run in USD", current.get("max_budget_usd", DEFAULTS["max_budget_usd"]))),
        "sandbox": ask_yn("Sandbox Bash (writes limited to the target repo, network blocked)", current.get("sandbox", True)),
        "concurrency": {
            "swe": int(ask("Max SWE tickets running concurrently", current["concurrency"]["swe"])),
            "qe": int(ask("Max QE running concurrently", current["concurrency"]["qe"])),
            "researcher": int(ask("Max Researcher spikes concurrently", current["concurrency"]["researcher"])),
            "tpm": int(ask("Max TPM scoping concurrently", current["concurrency"]["tpm"])),
        },
        "roles": {},
    }

    previous_default = current["roles"]["swe"]["model"]
    default_model = ask("Default model for all roles (sonnet/opus/haiku)", previous_default)
    for role in sorted(VALID_ROLES):
        role_current = current["roles"].get(role, DEFAULTS["roles"][role])
        if role in OPTIONAL_ROLES:
            enabled = ask_yn(f"Enable {role}", role_current["enabled"])
        else:
            enabled = True
        # Changing the default re-seeds every role; keeping it pre-fills each role's current model.
        role_default = default_model if default_model != previous_default else role_current.get("model", default_model)
        model = ask(f"Model for {role}", role_default)
        config["roles"][role] = {"enabled": enabled, "model": model}

    save_config(config)
    print(f"\nWrote {CONFIG_PATH.name}. Edit it by hand any time, or re-run this wizard.")


if __name__ == "__main__":
    main()
