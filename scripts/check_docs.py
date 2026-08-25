"""Validate local documentation links without adding a documentation dependency."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRECTORIES = {
    ".astro",
    ".git",
    ".npm-cache",
    ".pytest-state",
    ".pytest-tmp",
    ".pytest_cache",
    ".python",
    ".uv-cache",
    ".venv",
    "dist",
    "node_modules",
}
IGNORED_DIRECTORY_PREFIXES = (".pytest-state-", ".pytest-tmp-", ".uv-cache-")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
LEGACY_REPOSITORY_PREFIX = re.compile(r"""(?:link:\s+|(?:href|src)=["']|\]\()/BearAgent/""")
MARKDOWN_SUFFIXES = {".md", ".mdx"}
SITE_CONTENT_RELATIVE = Path("site/src/content/docs")
SITE_PUBLIC_RELATIVE = Path("site/public")
SITE_ROUTE_PREFIX = "/zh-cn/"


def markdown_files(root: Path = ROOT) -> list[Path]:
    """Return repository Markdown/MDX files while excluding generated environments."""
    files: list[Path] = []
    for directory, directory_names, file_names in os.walk(root, topdown=True):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in IGNORED_DIRECTORIES
            and not any(name.startswith(prefix) for prefix in IGNORED_DIRECTORY_PREFIXES)
        )
        files.extend(
            Path(directory) / name
            for name in file_names
            if Path(name).suffix.casefold() in MARKDOWN_SUFFIXES
        )
    return sorted(files)


def local_link_target(raw_target: str) -> str | None:
    """Return the path component for a local link or None for external/anchor links."""
    target = raw_target.strip().strip("<>")
    parsed = urlsplit(target)
    if parsed.scheme or target.startswith("#"):
        return None
    return unquote(parsed.path)


def broken_links(root: Path = ROOT) -> list[str]:
    """Collect missing local targets and source-style links that break site routes."""
    errors: list[str] = []
    site_content = (root / SITE_CONTENT_RELATIVE).resolve()
    for document in markdown_files(root):
        content = document.read_text(encoding="utf-8")
        if document.resolve().is_relative_to(site_content) and LEGACY_REPOSITORY_PREFIX.search(
            content
        ):
            relative_document = document.relative_to(root)
            errors.append(
                f"{relative_document}: site route must not include legacy /BearAgent prefix"
            )
        for match in MARKDOWN_LINK.finditer(content):
            target = local_link_target(match.group(1))
            if not target:
                continue
            is_site_document = document.resolve().is_relative_to(site_content)
            if is_site_document and target.startswith(SITE_ROUTE_PREFIX):
                route_target = site_content / target.removeprefix("/")
                route_sources = (
                    route_target.with_suffix(".md"),
                    route_target.with_suffix(".mdx"),
                    route_target / "index.md",
                    route_target / "index.mdx",
                )
                if any(candidate.exists() for candidate in route_sources):
                    continue
                relative_document = document.relative_to(root)
                errors.append(f"{relative_document}: missing site route {match.group(1)!r}")
                continue
            if is_site_document and target.startswith("/"):
                resolved = (root / SITE_PUBLIC_RELATIVE / target.removeprefix("/")).resolve()
            else:
                resolved = (document.parent / target).resolve()
            is_site_target = resolved.is_relative_to(site_content)
            if is_site_document and is_site_target:
                if resolved.suffix.casefold() in MARKDOWN_SUFFIXES:
                    relative_document = document.relative_to(root)
                    errors.append(
                        f"{relative_document}: site route must not include source suffix "
                        f"{match.group(1)!r}"
                    )
                    continue
                relative_document = document.relative_to(root)
                errors.append(
                    f"{relative_document}: internal site link must use /zh-cn/ "
                    f"route {match.group(1)!r}"
                )
                continue
            if not resolved.exists():
                relative_document = document.relative_to(root)
                errors.append(f"{relative_document}: missing target {match.group(1)!r}")
    return errors


def main() -> int:
    """Run the documentation check and return a process status."""
    errors = broken_links()
    if errors:
        print("Broken local Markdown links:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Checked {len(markdown_files())} Markdown files: local links OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
