import json
from pathlib import Path

from bearagent.domain.schema import public_domain_schemas

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "domain_schemas.json"


def test_public_domain_schemas_match_compatibility_snapshot() -> None:
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    assert public_domain_schemas() == expected
