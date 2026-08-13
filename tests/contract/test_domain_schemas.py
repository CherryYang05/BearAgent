import json
import os
from pathlib import Path

from bearagent.domain.schema import public_domain_schemas

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "domain_schemas.json"


def test_public_domain_schemas_match_compatibility_snapshot() -> None:
    actual = public_domain_schemas()
    if os.environ.get("UPDATE_DOMAIN_SCHEMA_SNAPSHOT") == "1":
        SNAPSHOT_PATH.write_text(
            json.dumps(actual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    assert actual == expected
