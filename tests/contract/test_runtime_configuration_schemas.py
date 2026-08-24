import json
from pathlib import Path

from bearagent.bootstrap import load_provider_catalog, load_run_profile
from bearagent.reference_schemas import public_runtime_configuration_schemas

REPOSITORY_ROOT = Path(__file__).parents[2]
SNAPSHOT_PATH = (
    REPOSITORY_ROOT / "tests" / "contract" / "snapshots" / "runtime_configuration_schemas.json"
)


def test_runtime_configuration_schema_snapshot_is_current() -> None:
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    assert public_runtime_configuration_schemas() == expected


def test_committed_v1_and_v2_configuration_examples_validate() -> None:
    examples = REPOSITORY_ROOT / "examples"

    assert load_run_profile(examples / "run-profile-v1.example.json").schema_version == 1
    assert load_run_profile(examples / "run-profile-v2.example.json").schema_version == 2
    assert load_provider_catalog(REPOSITORY_ROOT / "config.example.json").schema_version == 1
