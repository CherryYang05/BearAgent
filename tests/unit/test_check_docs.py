from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

from scripts import check_docs


def test_markdown_files_prunes_ignored_directories_before_descending(
    tmp_path: Path,
) -> None:
    def fake_walk(root: Path, *, topdown: bool) -> Iterator[tuple[str, list[str], list[str]]]:
        assert root == tmp_path
        assert topdown is True

        directory_names = [".venv", "docs"]
        yield str(root), directory_names, []

        assert directory_names == ["docs"]
        yield str(root / "docs"), [], ["visible.md"]

    with patch.object(check_docs.os, "walk", fake_walk):
        assert check_docs.markdown_files(tmp_path) == [tmp_path / "docs" / "visible.md"]
