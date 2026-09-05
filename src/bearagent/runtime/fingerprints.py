"""Deterministic hashing for trusted Run contract declarations."""

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import cast

from pydantic import JsonValue

from bearagent.domain.fingerprints import PolicyFingerprint, RunFingerprint, ToolFingerprint
from bearagent.domain.tools import ToolSpec


def policy_fingerprint(
    *,
    version: str,
    contract: Mapping[str, JsonValue],
) -> PolicyFingerprint:
    """Identify a bounded static Policy contract without persisting the contract body."""
    return PolicyFingerprint(version=version, sha256=canonical_sha256(contract))


def tool_fingerprint(spec: ToolSpec) -> ToolFingerprint:
    """Identify the exact declared registration-time ToolSpec."""
    contract = cast(dict[str, JsonValue], spec.model_dump(mode="json"))
    return ToolFingerprint(
        name=spec.name,
        spec_version=spec.spec_version,
        sha256=canonical_sha256(contract),
    )


def build_run_fingerprint(
    *,
    bearagent_version: str,
    policy: PolicyFingerprint,
    tool_specs: Iterable[ToolSpec],
) -> RunFingerprint:
    """Build one stable Run identity from trusted composition inputs."""
    tools = tuple(
        sorted((tool_fingerprint(spec) for spec in tool_specs), key=lambda item: item.name)
    )
    return RunFingerprint(
        bearagent_version=bearagent_version,
        policy=policy,
        tools=tools,
    )


def canonical_sha256(value: Mapping[str, JsonValue]) -> str:
    """Hash canonical UTF-8 JSON rather than Python object representations."""
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
