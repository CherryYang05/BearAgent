"""Regenerate the committed CLI result schema compatibility snapshot."""

import json
from pathlib import Path

from bearagent.interfaces.cli.contracts import public_cli_schemas

SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[1] / "tests" / "contract" / "snapshots" / "cli_schemas.json"
)


def main() -> None:
    """Write deterministic, reviewable JSON for all public CLI result models."""
    content = json.dumps(public_cli_schemas(), indent=2, ensure_ascii=False) + "\n"
    SNAPSHOT_PATH.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
