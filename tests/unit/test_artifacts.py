import pytest
from pydantic import ValidationError

from bearagent.domain.artifacts import Artifact, ArtifactEncoding, ArtifactKind
from bearagent.domain.ids import ArtifactId


def test_text_artifact_is_frozen_and_serializable() -> None:
    artifact = Artifact(
        artifact_id=ArtifactId.new(),
        path="outputs/intro.md",
        kind=ArtifactKind.TEXT,
        encoding=ArtifactEncoding.UTF8,
        size_bytes=12,
        sha256="a" * 64,
    )

    serialized = artifact.model_dump(mode="json")

    assert serialized["path"] == "outputs/intro.md"
    assert serialized["kind"] == "text"
    assert serialized["encoding"] == "utf-8"
    assert Artifact.model_validate(serialized) == artifact
    with pytest.raises(ValidationError):
        artifact.size_bytes = 13  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("path", ""),
        ("path", "   "),
        ("path", "outputs/bad\x00name.txt"),
        ("path", "outputs/" + "x" * 4_097),
        ("kind", "binary"),
        ("encoding", "utf-16"),
        ("size_bytes", -1),
        ("size_bytes", True),
        ("sha256", "A" * 64),
        ("sha256", "a" * 63),
    ],
)
def test_artifact_rejects_invalid_metadata(field: str, value: object) -> None:
    data: dict[str, object] = {
        "artifact_id": ArtifactId.new(),
        "path": "outputs/intro.md",
        "kind": "text",
        "encoding": "utf-8",
        "size_bytes": 12,
        "sha256": "a" * 64,
    }
    data[field] = value

    with pytest.raises(ValidationError):
        Artifact.model_validate(data)


def test_artifact_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Artifact.model_validate(
            {
                "artifact_id": ArtifactId.new(),
                "path": "outputs/intro.md",
                "kind": "text",
                "encoding": "utf-8",
                "size_bytes": 12,
                "sha256": "a" * 64,
                "grant": "write-anywhere",
            }
        )
