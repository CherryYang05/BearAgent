import json
from pathlib import Path

from bearagent.interfaces.cli.contracts import public_cli_schemas

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "cli_schemas.json"


def test_public_cli_schemas_match_compatibility_snapshot() -> None:
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    assert public_cli_schemas() == expected
