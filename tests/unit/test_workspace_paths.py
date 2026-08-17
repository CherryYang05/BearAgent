import pytest

from bearagent.adapters.tools import normalize_workspace_path


@pytest.mark.parametrize(
    ("raw_path", "expected"),
    [
        (".", "."),
        ("./docs//guide.md", "docs/guide.md"),
        (r"docs\guide.md", "docs/guide.md"),
        (r"docs\nested/guide.md", "docs/nested/guide.md"),
        ("资料/说明.md", "资料/说明.md"),
    ],
)
def test_normalize_workspace_path_accepts_both_host_separators(
    raw_path: str, expected: str
) -> None:
    assert normalize_workspace_path(raw_path) == expected


@pytest.mark.parametrize(
    "raw_path",
    [
        "",
        "/etc/passwd",
        r"\server\share\secret.txt",
        r"\rooted.txt",
        r"C:\secret.txt",
        "C:/secret.txt",
        "../secret.txt",
        "docs/../secret.txt",
        "docs/NUL.txt",
        "docs/report:stream",
        "docs/trailing.",
        "docs/trailing ",
        "docs/control\nname",
    ],
)
def test_normalize_workspace_path_rejects_non_portable_or_escaping_paths(
    raw_path: str,
) -> None:
    with pytest.raises(ValueError):
        normalize_workspace_path(raw_path)


def test_normalize_workspace_path_enforces_path_and_segment_limits() -> None:
    with pytest.raises(ValueError, match="segment exceeds"):
        normalize_workspace_path("x" * 256)
    with pytest.raises(ValueError, match="too many segments"):
        normalize_workspace_path("/".join("x" for _ in range(65)))
    with pytest.raises(ValueError, match="path exceeds"):
        normalize_workspace_path("/".join("x" * 20 for _ in range(60)))
