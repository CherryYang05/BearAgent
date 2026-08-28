"""Finite identities for the trusted contracts used by one Run."""

from typing import Self

from pydantic import Field, model_validator

from bearagent.domain._base import DomainModel
from bearagent.domain.messages import TOOL_NAME_PATTERN

CONTRACT_VERSION_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$"
BEARAGENT_VERSION_PATTERN = CONTRACT_VERSION_PATTERN
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class PolicyFingerprint(DomainModel):
    """Identity of one trusted static Policy evaluator and configuration."""

    version: str = Field(pattern=CONTRACT_VERSION_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)


class ToolFingerprint(DomainModel):
    """Identity of one registration-time Tool contract."""

    name: str = Field(pattern=TOOL_NAME_PATTERN)
    spec_version: str = Field(pattern=CONTRACT_VERSION_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)


class RunFingerprint(DomainModel):
    """Trusted contract provenance captured once when a Run is created."""

    bearagent_version: str = Field(pattern=BEARAGENT_VERSION_PATTERN)
    policy: PolicyFingerprint
    tools: tuple[ToolFingerprint, ...] = ()

    @model_validator(mode="after")
    def require_unique_sorted_tools(self) -> Self:
        names = tuple(tool.name for tool in self.tools)
        if len(names) != len(set(names)):
            raise ValueError("Run fingerprint Tool names must be unique")
        if names != tuple(sorted(names)):
            raise ValueError("Run fingerprint Tools must be sorted by name")
        return self
