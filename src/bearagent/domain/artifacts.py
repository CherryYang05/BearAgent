"""Provider-neutral metadata for retrievable Run outputs."""

from enum import StrEnum

from pydantic import Field, field_validator

from bearagent.domain._base import DomainModel
from bearagent.domain.ids import ArtifactId

MAX_ARTIFACT_PATH_BYTES = 4_096
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ArtifactKind(StrEnum):
    """Stable high-level representation of one Artifact."""

    TEXT = "text"


class ArtifactEncoding(StrEnum):
    """Encoding used by a text Artifact."""

    UTF8 = "utf-8"


class Artifact(DomainModel):
    """Bounded metadata for one retrievable output, without access authority."""

    artifact_id: ArtifactId
    path: str = Field(min_length=1, max_length=MAX_ARTIFACT_PATH_BYTES)
    kind: ArtifactKind
    encoding: ArtifactEncoding
    size_bytes: int = Field(ge=0, strict=True)
    sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("path")
    @classmethod
    def require_safe_bounded_metadata_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Artifact path must not be blank")
        if len(value.encode("utf-8")) > MAX_ARTIFACT_PATH_BYTES:
            raise ValueError("Artifact path exceeds the byte limit")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("Artifact path contains a control character")
        return value
