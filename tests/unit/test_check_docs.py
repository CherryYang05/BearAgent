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

        directory_names = [
            ".pytest-state",
            ".pytest-tmp",
            ".pytest_cache",
            ".uv-cache-docs",
            ".venv",
            "docs",
        ]
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
        "[good](/zh-cn/guides/cli/)\n[broken](../guides/cli.md)\n",
        encoding="utf-8",
    )

    relative_source = source.relative_to(tmp_path)
    assert check_docs.broken_links(tmp_path) == [
        f"{relative_source}: site route must not include source suffix '../guides/cli.md'"
    ]


def test_site_routes_reject_legacy_repository_prefix(tmp_path: Path) -> None:
    site = tmp_path / "site" / "src" / "content" / "docs" / "zh-cn"
    site.mkdir(parents=True)
    source = site / "index.mdx"
    source.write_text("hero:\n  link: /BearAgent/zh-cn/guides/cli/\n", encoding="utf-8")

    relative_source = source.relative_to(tmp_path)
    assert check_docs.broken_links(tmp_path) == [
        f"{relative_source}: site route must not include legacy /BearAgent prefix"
    ]


def test_site_root_asset_resolves_from_public_directory(tmp_path: Path) -> None:
    site_root = tmp_path / "site"
    source = site_root / "src" / "content" / "docs" / "zh-cn" / "index.md"
    image = site_root / "public" / "images" / "cover.jpg"
    source.parent.mkdir(parents=True)
    image.parent.mkdir(parents=True)
    source.write_text("![cover](/images/cover.jpg)\n", encoding="utf-8")
    image.write_bytes(b"image")

    assert check_docs.broken_links(tmp_path) == []
