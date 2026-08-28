"""Validate Spec, Plan, ADR, and documentation governance invariants."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_DIRECTORY = ROOT / "docs" / "specs"
PLAN_DIRECTORY = ROOT / "docs" / "plans"
ADR_DIRECTORY = ROOT / "docs" / "adr"
SITE_DIRECTORY = ROOT / "site" / "src" / "content" / "docs"

SPEC_ID = re.compile(r"^F-\d{4}$")
PLAN_ID = re.compile(r"^PLAN-F-\d{4}$")
ADR_ID = re.compile(r"^ADR-\d{4}$")
MILESTONE_ID = re.compile(r"^P\d+$")
UNCHECKED_ITEM = re.compile(r"^\s*- \[ \]", re.MULTILINE)
PULL_REQUEST_EVIDENCE = re.compile(r"(?:\bPR #\d+\b|/pull/\d+\b)")
COMMIT_EVIDENCE = re.compile(r"(?:\bcommit[ /]|\b)[0-9a-f]{7,40}\b", re.IGNORECASE)
SPEC_INDEX_ENTRY = re.compile(
    r"\[(F-\d{4})[^\]]*\]\(([^)]+)\)\s+—\s+(draft|accepted|implemented|superseded)"
)
MARKDOWN_LINK = re.compile(r"\[((?:PLAN-)?F-\d{4}|ADR-\d{4})[^\]]*\]\(([^)]+)\)")

SPEC_STATUSES = {"draft", "accepted", "implemented", "superseded"}
PLAN_STATUSES = {"draft", "active", "completed", "superseded"}
ADR_STATUSES = {"proposed", "accepted", "deprecated", "superseded"}
CHANGE_LEVELS = {"S1", "S2"}

FrontMatterValue = str | tuple[str, ...]


@dataclass(frozen=True)
class Document:
    """A Markdown document with the small Front Matter subset used by BearAgent."""

    path: Path
    metadata: dict[str, FrontMatterValue]
    body: str


def load_document(path: Path) -> Document:
    """Read one document and parse scalar and string-list Front Matter fields."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("missing opening Front Matter delimiter")
    try:
        closing_index = lines.index("---", 1)
    except ValueError as cause:
        raise ValueError("missing closing Front Matter delimiter") from cause
    metadata = _parse_front_matter(lines[1:closing_index])
    body = "\n".join(lines[closing_index + 1 :])
    return Document(path=path, metadata=metadata, body=body)


def _parse_front_matter(lines: list[str]) -> dict[str, FrontMatterValue]:
    metadata: dict[str, FrontMatterValue] = {}
    list_key: str | None = None
    for line in lines:
        if line.startswith("  - ") and list_key is not None:
            current = metadata[list_key]
            if not isinstance(current, tuple):
                raise ValueError(f"Front Matter field {list_key!r} mixes scalar and list values")
            metadata[list_key] = (*current, _unquote(line.removeprefix("  - ").strip()))
            continue
        if line.startswith((" ", "\t")) or ":" not in line:
            list_key = None
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            raise ValueError("Front Matter contains an empty key")
        if not value:
            metadata[key] = ()
            list_key = key
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            metadata[key] = (
                () if not inner else tuple(_unquote(item.strip()) for item in inner.split(","))
            )
            list_key = None
        else:
            metadata[key] = _unquote(value)
            list_key = None
    return metadata


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _scalar(document: Document, key: str, errors: list[str]) -> str | None:
    value = document.metadata.get(key)
    if value is None:
        errors.append(f"{_relative(document.path)}: missing Front Matter field {key!r}")
        return None
    if isinstance(value, tuple):
        errors.append(f"{_relative(document.path)}: Front Matter field {key!r} must be scalar")
        return None
    return value


def _string_list(document: Document, key: str, errors: list[str]) -> tuple[str, ...]:
    value = document.metadata.get(key, ())
    if isinstance(value, tuple):
        return value
    errors.append(f"{_relative(document.path)}: Front Matter field {key!r} must be a list")
    return ()


def _load_documents(directory: Path, pattern: str, errors: list[str]) -> list[Document]:
    documents: list[Document] = []
    for path in sorted(directory.glob(pattern)):
        try:
            documents.append(load_document(path))
        except ValueError as cause:
            errors.append(f"{_relative(path)}: {cause}")
    return documents


def governance_errors() -> list[str]:
    """Return every deterministic governance violation in the repository."""
    errors: list[str] = []
    spec_documents = _load_documents(SPEC_DIRECTORY, "F-*.md", errors)
    plan_documents = _load_documents(PLAN_DIRECTORY, "PLAN-F-*.md", errors)
    adr_documents = _load_documents(ADR_DIRECTORY, "ADR-*.md", errors)

    specs = _validate_specs(spec_documents, errors)
    plans = _validate_plans(plan_documents, specs, errors)
    adrs = _validate_adrs(adr_documents, errors)
    _validate_spec_relationships(specs, plans, adrs, errors)
    _validate_spec_index(specs, errors)
    _validate_plan_index(plans, errors)
    _validate_adr_index(adrs, errors)
    _validate_site_source_refs(specs, plans, adrs, errors)
    return sorted(errors)


def _validate_specs(documents: list[Document], errors: list[str]) -> dict[str, Document]:
    specs: dict[str, Document] = {}
    for document in documents:
        spec_id = _scalar(document, "spec_id", errors)
        status = _scalar(document, "status", errors)
        milestone = _scalar(document, "milestone", errors)
        change_level = document.metadata.get("change_level")
        if spec_id is None:
            continue
        if not SPEC_ID.fullmatch(spec_id):
            errors.append(f"{_relative(document.path)}: invalid spec_id {spec_id!r}")
            continue
        if spec_id in specs:
            errors.append(f"{_relative(document.path)}: duplicate spec_id {spec_id}")
        else:
            specs[spec_id] = document
        if not document.path.name.startswith(f"{spec_id}-"):
            errors.append(f"{_relative(document.path)}: filename does not begin with {spec_id}-")
        if status not in SPEC_STATUSES:
            errors.append(f"{_relative(document.path)}: invalid Feature status {status!r}")
        if milestone is None or not MILESTONE_ID.fullmatch(milestone):
            errors.append(f"{_relative(document.path)}: invalid milestone {milestone!r}")
        if change_level is not None and change_level not in CHANGE_LEVELS:
            errors.append(f"{_relative(document.path)}: invalid change_level {change_level!r}")
        if status == "implemented":
            implemented_in = _scalar(document, "implemented_in", errors)
            if implemented_in in {None, "", "null"}:
                errors.append(
                    f"{_relative(document.path)}: implemented Feature needs immutable evidence"
                )
            elif implemented_in is not None and not _has_immutable_evidence(implemented_in):
                errors.append(
                    f"{_relative(document.path)}: implemented_in must name a PR or commit"
                )
            if UNCHECKED_ITEM.search(document.body):
                errors.append(
                    f"{_relative(document.path)}: implemented Feature contains unchecked items"
                )
    return specs


def _validate_plans(
    documents: list[Document],
    specs: dict[str, Document],
    errors: list[str],
) -> dict[str, Document]:
    plans: dict[str, Document] = {}
    active_paths: list[Path] = []
    for document in documents:
        plan_id = _scalar(document, "plan_id", errors)
        status = _scalar(document, "status", errors)
        related_spec = _scalar(document, "related_spec", errors)
        if plan_id is None:
            continue
        if not PLAN_ID.fullmatch(plan_id):
            errors.append(f"{_relative(document.path)}: invalid plan_id {plan_id!r}")
            continue
        if plan_id in plans:
            errors.append(f"{_relative(document.path)}: duplicate plan_id {plan_id}")
        else:
            plans[plan_id] = document
        if not document.path.name.startswith(f"{plan_id}-"):
            errors.append(f"{_relative(document.path)}: filename does not begin with {plan_id}-")
        if status not in PLAN_STATUSES:
            errors.append(f"{_relative(document.path)}: invalid Plan status {status!r}")
        if related_spec is None or not SPEC_ID.fullmatch(related_spec):
            errors.append(f"{_relative(document.path)}: invalid related_spec {related_spec!r}")
        elif related_spec not in specs:
            errors.append(f"{_relative(document.path)}: unknown related_spec {related_spec}")
        if status == "active":
            active_paths.append(document.path)
        if status == "completed" and UNCHECKED_ITEM.search(document.body):
            errors.append(f"{_relative(document.path)}: completed Plan contains unchecked items")
    if len(active_paths) > 1:
        joined = ", ".join(_relative(path) for path in active_paths)
        errors.append(f"multiple active Plans: {joined}")
    return plans


def _validate_adrs(documents: list[Document], errors: list[str]) -> dict[str, Document]:
    adrs: dict[str, Document] = {}
    for document in documents:
        match = re.match(r"(ADR-\d{4})-", document.path.name)
        if match is None:
            errors.append(f"{_relative(document.path)}: invalid ADR filename")
            continue
        adr_id = match.group(1)
        status = _scalar(document, "status", errors)
        title = _scalar(document, "title", errors)
        if adr_id in adrs:
            errors.append(f"{_relative(document.path)}: duplicate ADR ID {adr_id}")
        else:
            adrs[adr_id] = document
        if status not in ADR_STATUSES:
            errors.append(f"{_relative(document.path)}: invalid ADR status {status!r}")
        if title is not None and not title.startswith(f"{adr_id}:"):
            errors.append(f"{_relative(document.path)}: title must begin with {adr_id}:")
    return adrs


def _validate_spec_relationships(
    specs: dict[str, Document],
    plans: dict[str, Document],
    adrs: dict[str, Document],
    errors: list[str],
) -> None:
    plans_by_spec: dict[str, list[Document]] = {}
    for plan in plans.values():
        related_spec = plan.metadata.get("related_spec")
        if not isinstance(related_spec, str) or related_spec not in specs:
            continue
        plans_by_spec.setdefault(related_spec, []).append(plan)
        plan_status = plan.metadata.get("status")
        spec_status = specs[related_spec].metadata.get("status")
        if plan_status == "active" and spec_status != "accepted":
            errors.append(
                f"{_relative(plan.path)}: active Plan requires accepted Feature {related_spec}"
            )
        if plan_status == "completed" and spec_status != "implemented":
            errors.append(
                f"{_relative(plan.path)}: completed Plan requires implemented Feature "
                f"{related_spec}"
            )

    for spec_id, spec in specs.items():
        status = spec.metadata.get("status")
        change_level = spec.metadata.get("change_level")
        related_adrs = _string_list(spec, "related_adrs", errors)
        related_plans = plans_by_spec.get(spec_id, [])
        if status == "implemented":
            for plan in related_plans:
                if plan.metadata.get("status") not in {"completed", "superseded"}:
                    errors.append(
                        f"{_relative(spec.path)}: implemented Feature has unfinished Plan "
                        f"{plan.metadata.get('plan_id')}"
                    )
        for adr_id in related_adrs:
            adr = adrs.get(adr_id)
            if adr is None:
                errors.append(f"{_relative(spec.path)}: unknown related ADR {adr_id}")
            elif status in {"accepted", "implemented"} and adr.metadata.get("status") not in {
                "accepted",
                "superseded",
            }:
                errors.append(f"{_relative(spec.path)}: related ADR {adr_id} is not accepted")
        if change_level == "S2" and status in {"accepted", "implemented"}:
            if not related_adrs:
                errors.append(f"{_relative(spec.path)}: S2 Feature requires a related ADR")
            required_plan_statuses = (
                {"active"}
                if status == "accepted"
                else {
                    "completed",
                    "superseded",
                }
            )
            if not any(
                plan.metadata.get("status") in required_plan_statuses for plan in related_plans
            ):
                expected = "active" if status == "accepted" else "completed"
                errors.append(f"{_relative(spec.path)}: S2 Feature requires Plan status {expected}")


def _validate_spec_index(specs: dict[str, Document], errors: list[str]) -> None:
    path = SPEC_DIRECTORY / "README.md"
    text = path.read_text(encoding="utf-8")
    entries: dict[str, tuple[str, str]] = {}
    for spec_id, target, status in SPEC_INDEX_ENTRY.findall(text):
        if spec_id in entries:
            errors.append(f"{_relative(path)}: duplicate index entry for {spec_id}")
        entries[spec_id] = (target, status)
    for spec_id, document in specs.items():
        entry = entries.get(spec_id)
        if entry is None:
            errors.append(f"{_relative(path)}: missing index entry for {spec_id}")
            continue
        target, status = entry
        if target != document.path.name:
            errors.append(f"{_relative(path)}: {spec_id} points to {target!r}")
        if status != document.metadata.get("status"):
            errors.append(
                f"{_relative(path)}: {spec_id} says {status}, "
                f"Front Matter says {document.metadata.get('status')}"
            )
    for spec_id in entries.keys() - specs.keys():
        errors.append(f"{_relative(path)}: unknown index entry {spec_id}")


def _validate_plan_index(plans: dict[str, Document], errors: list[str]) -> None:
    path = PLAN_DIRECTORY / "README.md"
    section: str | None = None
    entries: dict[str, tuple[str, str | None]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "## 当前计划":
            section = "current"
            continue
        if line == "## 已完成计划":
            section = "completed"
            continue
        match = MARKDOWN_LINK.search(line)
        if match is None or not match.group(1).startswith("PLAN-"):
            continue
        plan_id, target = match.groups()
        if plan_id in entries:
            errors.append(f"{_relative(path)}: duplicate index entry for {plan_id}")
        entries[plan_id] = (target, section)
    for plan_id, document in plans.items():
        entry = entries.get(plan_id)
        if entry is None:
            errors.append(f"{_relative(path)}: missing index entry for {plan_id}")
            continue
        target, entry_section = entry
        if target != document.path.name:
            errors.append(f"{_relative(path)}: {plan_id} points to {target!r}")
        status = document.metadata.get("status")
        expected_section = "completed" if status in {"completed", "superseded"} else "current"
        if entry_section != expected_section:
            errors.append(
                f"{_relative(path)}: {plan_id} is under {entry_section!r}, "
                f"expected {expected_section!r}"
            )
    for plan_id in entries.keys() - plans.keys():
        errors.append(f"{_relative(path)}: unknown index entry {plan_id}")


def _validate_adr_index(adrs: dict[str, Document], errors: list[str]) -> None:
    path = ADR_DIRECTORY / "README.md"
    entries: dict[str, str] = {}
    for adr_id, target in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
        if not adr_id.startswith("ADR-"):
            continue
        if adr_id in entries:
            errors.append(f"{_relative(path)}: duplicate index entry for {adr_id}")
        entries[adr_id] = target
    for adr_id, document in adrs.items():
        target = entries.get(adr_id)
        if target is None:
            errors.append(f"{_relative(path)}: missing index entry for {adr_id}")
        elif target != document.path.name:
            errors.append(f"{_relative(path)}: {adr_id} points to {target!r}")
    for adr_id in entries.keys() - adrs.keys():
        errors.append(f"{_relative(path)}: unknown index entry {adr_id}")


def _validate_site_source_refs(
    specs: dict[str, Document],
    plans: dict[str, Document],
    adrs: dict[str, Document],
    errors: list[str],
) -> None:
    for path in sorted((*SITE_DIRECTORY.rglob("*.md"), *SITE_DIRECTORY.rglob("*.mdx"))):
        try:
            document = load_document(path)
        except ValueError as cause:
            errors.append(f"{_relative(path)}: {cause}")
            continue
        for source_ref in _string_list(document, "sourceRefs", errors):
            unknown_internal_ref = (
                (SPEC_ID.fullmatch(source_ref) is not None and source_ref not in specs)
                or (PLAN_ID.fullmatch(source_ref) is not None and source_ref not in plans)
                or (ADR_ID.fullmatch(source_ref) is not None and source_ref not in adrs)
            )
            if unknown_internal_ref:
                errors.append(f"{_relative(path)}: unknown sourceRef {source_ref}")


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _has_immutable_evidence(value: str) -> bool:
    return (
        value == "initial repository commit"
        or PULL_REQUEST_EVIDENCE.search(value) is not None
        or COMMIT_EVIDENCE.search(value) is not None
    )


def main() -> int:
    """Run governance checks and return a process status."""
    errors = governance_errors()
    if errors:
        print("Governance errors:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    spec_count = len(tuple(SPEC_DIRECTORY.glob("F-*.md")))
    plan_count = len(tuple(PLAN_DIRECTORY.glob("PLAN-F-*.md")))
    adr_count = len(tuple(ADR_DIRECTORY.glob("ADR-*.md")))
    print(f"Checked governance: {spec_count} Specs, {plan_count} Plans, {adr_count} ADRs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
