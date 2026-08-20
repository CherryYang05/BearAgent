from pathlib import Path

import pytest
from scripts import check_docs


def test_markdown_files_ignore_isolated_pytest_workspaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "docs").mkdir()
    expected = tmp_path / "docs" / "index.md"
    expected.write_text("# Docs\n", encoding="utf-8")
    ignored = tmp_path / ".pytest-tmp-f0016-final" / "case" / "output.md"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("# Test output\n", encoding="utf-8")
    monkeypatch.setattr(check_docs, "ROOT", tmp_path)

    assert check_docs.markdown_files() == [expected]
