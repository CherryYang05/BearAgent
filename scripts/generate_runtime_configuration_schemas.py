"""Regenerate configuration and P1 evaluation schema compatibility snapshots."""

import json
from pathlib import Path

from bearagent.reference_schemas import public_runtime_configuration_schemas

SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "contract"
    / "snapshots"
    / "runtime_configuration_schemas.json"
)


def main() -> None:
    content = (
        json.dumps(
            public_runtime_configuration_schemas(),
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    SNAPSHOT_PATH.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
