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
    config = {
        "target_repo": ask("Repo this team operates on", current["target_repo"]),
        "house_rules": None if house_rules_answer.strip().lower() == "none" else house_rules_answer,
        "max_turns": int(ask("Max orchestrator nudge-turns before giving up", current["max_turns"])),
        "concurrency": {
            "swe": int(ask("Max SWE tickets running concurrently", current["concurrency"]["swe"])),
            "qe": int(ask("Max QE running concurrently", current["concurrency"]["qe"])),
            "researcher": int(ask("Max Researcher spikes concurrently", current["concurrency"]["researcher"])),
            "tpm": int(ask("Max TPM scoping concurrently", current["concurrency"]["tpm"])),
        },
        "roles": {},
    }

    default_model = ask("Default model for all roles (sonnet/opus/haiku)", current["roles"]["swe"]["model"])
    for role in sorted(VALID_ROLES):
        role_current = current["roles"].get(role, DEFAULTS["roles"][role])
        if role in OPTIONAL_ROLES:
            enabled = ask_yn(f"Enable {role}", role_current["enabled"])
        else:
            enabled = True
        model = ask(f"Model for {role}", role_current.get("model", default_model))
        config["roles"][role] = {"enabled": enabled, "model": model}

    save_config(config)
    print(f"\nWrote {CONFIG_PATH.name}. Edit it by hand any time, or re-run this wizard.")


if __name__ == "__main__":
    main()
