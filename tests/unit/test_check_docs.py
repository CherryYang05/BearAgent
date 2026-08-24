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

        directory_names = [".uv-cache-docs", ".venv", "docs"]
        yield str(root), directory_names, []

        assert directory_names == ["docs"]
        yield str(root / "docs"), [], ["visible.md"]

    with patch.object(check_docs.os, "walk", fake_walk):
        assert check_docs.markdown_files(tmp_path) == [tmp_path / "docs" / "visible.md"]


def test_markdown_files_includes_mdx(tmp_path: Path) -> None:
    (tmp_path / "index.mdx").write_text("# Home", encoding="utf-8")

    assert check_docs.markdown_files(tmp_path) == [tmp_path / "index.mdx"]


def test_site_links_use_built_routes_instead_of_source_suffixes(tmp_path: Path) -> None:
    learn = tmp_path / "site" / "src" / "content" / "docs" / "zh-cn" / "learn"
    guides = learn.parent / "guides"
    learn.mkdir(parents=True)
    guides.mkdir()
    (guides / "cli.md").write_text("# CLI", encoding="utf-8")
    source = learn / "index.md"
    source.write_text(
        "[good](/BearAgent/zh-cn/guides/cli/)\n[broken](../guides/cli.md)\n",
        encoding="utf-8",
    )

    relative_source = source.relative_to(tmp_path)
    assert check_docs.broken_links(tmp_path) == [
        f"{relative_source}: site route must not include source suffix '../guides/cli.md'"
    ]


def test_site_absolute_routes_include_base_prefix(tmp_path: Path) -> None:
    site = tmp_path / "site" / "src" / "content" / "docs" / "zh-cn"
    site.mkdir(parents=True)
    source = site / "index.mdx"
    source.write_text("hero:\n  link: /zh-cn/guides/cli/\n", encoding="utf-8")

    relative_source = source.relative_to(tmp_path)
    assert check_docs.broken_links(tmp_path) == [
        f"{relative_source}: absolute site route must include /BearAgent prefix"
    ]
