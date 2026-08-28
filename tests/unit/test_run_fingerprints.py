import pytest
from pydantic import JsonValue, ValidationError
from tests.tool_fixtures import build_tool_spec

from bearagent.domain.fingerprints import (
    PolicyFingerprint,
    RunFingerprint,
    ToolFingerprint,
)
from bearagent.runtime.fingerprints import (
    build_run_fingerprint,
    canonical_sha256,
    tool_fingerprint,
)
from bearagent.runtime.policy import FixedToolPolicy


def test_canonical_sha256_ignores_mapping_insertion_order() -> None:
    first: dict[str, JsonValue] = {"name": "workspace.read", "version": "1"}
    second: dict[str, JsonValue] = {"version": "1", "name": "workspace.read"}

    assert canonical_sha256(first) == canonical_sha256(second)


def test_fixed_policy_fingerprint_is_stable_for_allowlist_order() -> None:
    first = FixedToolPolicy(["workspace.read", "workspace.list"])
    second = FixedToolPolicy(["workspace.list", "workspace.read"])

    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != FixedToolPolicy(["workspace.read"]).fingerprint


def test_run_fingerprint_sorts_tools_and_detects_contract_changes() -> None:
    read = build_tool_spec(name="workspace.read")
    listed = build_tool_spec(name="workspace.list")
    policy = FixedToolPolicy([read.name, listed.name])

    first = build_run_fingerprint(
        bearagent_version="0.1.0+test",
        policy=policy.fingerprint,
        tool_specs=[read, listed],
    )
    second = build_run_fingerprint(
        bearagent_version="0.1.0+test",
        policy=policy.fingerprint,
        tool_specs=[listed, read],
    )

    changed = read.model_copy(update={"spec_version": "2"})

    assert first == second
    assert tuple(tool.name for tool in first.tools) == ("workspace.list", "workspace.read")
    assert tool_fingerprint(read) != tool_fingerprint(changed)


def test_run_fingerprint_rejects_duplicate_or_unsorted_tools() -> None:
    policy = PolicyFingerprint(version="policy-v1", sha256="a" * 64)
    read = ToolFingerprint(
        name="workspace.read",
        spec_version="1",
        sha256="b" * 64,
    )
    listed = ToolFingerprint(
        name="workspace.list",
        spec_version="1",
        sha256="c" * 64,
    )

    with pytest.raises(ValidationError, match="sorted by name"):
        RunFingerprint(
            bearagent_version="0.1.0",
            policy=policy,
            tools=(read, listed),
        )
    with pytest.raises(ValidationError, match="must be unique"):
        RunFingerprint(
            bearagent_version="0.1.0",
            policy=policy,
            tools=(read, read),
        )


def test_fingerprint_rejects_non_sha256_text() -> None:
    with pytest.raises(ValidationError):
        PolicyFingerprint(version="policy-v1", sha256="not-a-sha256")


def test_run_fingerprint_rejects_configuration_and_authority_fields() -> None:
    valid = build_run_fingerprint(
        bearagent_version="0.1.0+test",
        policy=FixedToolPolicy(["workspace.read"]).fingerprint,
        tool_specs=(build_tool_spec(),),
    ).model_dump(mode="json")

    with pytest.raises(ValidationError):
        RunFingerprint.model_validate(
            {
                **valid,
                "workspace_path": "C:/private/workspace",
                "api_key": "must-not-be-stored",
                "grant": {"tool": "workspace.write"},
            }
        )
