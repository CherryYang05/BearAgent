"""Validate local Markdown links without adding a documentation dependency."""

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
    ".python",
    ".uv-cache",
    ".venv",
    "dist",
    "node_modules",
}
IGNORED_DIRECTORY_PREFIXES = (".pytest-state-", ".pytest-tmp-")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def markdown_files(root: Path = ROOT) -> list[Path]:
    """Return repository Markdown files while excluding generated environments."""
    files: list[Path] = []
    for directory, directory_names, file_names in os.walk(root, topdown=True):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in IGNORED_DIRECTORIES
            and not any(name.startswith(prefix) for prefix in IGNORED_DIRECTORY_PREFIXES)
        )
        files.extend(
            Path(directory) / name for name in file_names if name.casefold().endswith(".md")
        )
    return sorted(files)


def local_link_target(raw_target: str) -> str | None:
    """Return the path component for a local link or None for external/anchor links."""
    target = raw_target.strip().strip("<>")
    parsed = urlsplit(target)
    if parsed.scheme or target.startswith("#"):
        return None
    return unquote(parsed.path)


def broken_links() -> list[str]:
    """Collect every missing local Markdown target."""
    errors: list[str] = []
    for document in markdown_files():
        content = document.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(content):
            target = local_link_target(match.group(1))
            if not target:
                continue
            resolved = (document.parent / target).resolve()
            if not resolved.exists():
                relative_document = document.relative_to(ROOT)
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
