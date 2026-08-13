import pytest
from tests.tool_fixtures import build_tool_request, build_tool_spec

from bearagent.domain.tools import (
    PolicyOutcome,
    PolicyReason,
    PreparedToolRequest,
    ToolSideEffect,
)
from bearagent.runtime.policy import FixedToolPolicy


def prepared_request(name: str = "workspace.read") -> PreparedToolRequest:
    request = build_tool_request(name=name)
    return PreparedToolRequest.model_validate(request.model_dump(mode="json"))


def test_policy_denies_by_default() -> None:
    decision = FixedToolPolicy().evaluate(build_tool_spec(), prepared_request())

    assert decision.outcome is PolicyOutcome.DENY
    assert decision.reason is PolicyReason.TOOL_NOT_ALLOWED


def test_policy_allows_configured_read_and_workspace_write() -> None:
    policy = FixedToolPolicy(["workspace.read", "workspace.write"])

    read = policy.evaluate(build_tool_spec(), prepared_request())
    write = policy.evaluate(
        build_tool_spec(name="workspace.write", side_effect=ToolSideEffect.WORKSPACE_WRITE),
        prepared_request("workspace.write"),
    )

    assert read.outcome is PolicyOutcome.ALLOW
    assert write.outcome is PolicyOutcome.ALLOW


@pytest.mark.parametrize(
    "side_effect",
    [ToolSideEffect.EXTERNAL_WRITE, ToolSideEffect.CODE_EXECUTION],
)
def test_policy_hard_denies_dangerous_side_effects(side_effect: ToolSideEffect) -> None:
    policy = FixedToolPolicy(["danger.run"])

    decision = policy.evaluate(
        build_tool_spec(name="danger.run", side_effect=side_effect),
        prepared_request("danger.run"),
    )

    assert decision.outcome is PolicyOutcome.DENY
    assert decision.reason is PolicyReason.SIDE_EFFECT_DENIED


def test_model_arguments_and_external_mutation_cannot_expand_allowlist() -> None:
    allowed = ["workspace.read"]
    policy = FixedToolPolicy(allowed)
    allowed.append("danger.run")
    request = build_tool_request(
        name="danger.run",
        arguments={"allow": True, "grant": "danger.run"},
    )

    decision = policy.evaluate(
        build_tool_spec(name="danger.run"),
        PreparedToolRequest.model_validate(request.model_dump(mode="json")),
    )

    assert decision.outcome is PolicyOutcome.DENY
    assert policy.allowed_tool_names == frozenset({"workspace.read"})


def test_policy_denies_mismatched_prepared_request() -> None:
    decision = FixedToolPolicy(["workspace.read"]).evaluate(
        build_tool_spec(),
        prepared_request("workspace.search"),
    )

    assert decision.outcome is PolicyOutcome.DENY


def test_policy_rejects_one_string_as_an_allowlist_collection() -> None:
    with pytest.raises(ValueError, match="must be a collection"):
        FixedToolPolicy("workspace.read")
