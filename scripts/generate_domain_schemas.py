"""Regenerate the committed public domain schema compatibility snapshot."""

import json
from pathlib import Path

from bearagent.domain.schema import public_domain_schemas

SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[1] / "tests" / "contract" / "snapshots" / "domain_schemas.json"
)


def main() -> None:
    """Write deterministic, reviewable JSON for all public domain models."""
    content = json.dumps(public_domain_schemas(), indent=2, ensure_ascii=False) + "\n"
    SNAPSHOT_PATH.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
