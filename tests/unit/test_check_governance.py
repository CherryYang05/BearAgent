from pathlib import Path

import pytest
from scripts import check_governance


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _spec(
    *,
    status: str = "implemented",
    checklist: str = "- [x] Docs reviewed",
    implemented_in: str = "PR #1",
    change_level: str | None = None,
) -> str:
    change_level_line = "" if change_level is None else f"change_level: {change_level}\n"
    return f"""---
title: "Feature: Example"
status: {status}
spec_id: F-0001
milestone: P1
{change_level_line}owner: CherryYang
created: 2026-08-27
last_updated: 2026-08-27
implemented_in: "{implemented_in}"
related_adrs: [ADR-0001]
---

# F-0001: Example

{checklist}
"""


def _plan(*, status: str = "completed") -> str:
    return f"""---
title: "Implementation Plan: Example"
status: {status}
plan_id: PLAN-F-0001
related_spec: F-0001
created: 2026-08-27
last_updated: 2026-08-27
---

# PLAN-F-0001: Example

- [x] Verified
"""


def _configure_repository(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(check_governance, "ROOT", root)
    monkeypatch.setattr(check_governance, "SPEC_DIRECTORY", root / "docs" / "specs")
    monkeypatch.setattr(check_governance, "PLAN_DIRECTORY", root / "docs" / "plans")
    monkeypatch.setattr(check_governance, "ADR_DIRECTORY", root / "docs" / "adr")
    monkeypatch.setattr(
        check_governance,
        "SITE_DIRECTORY",
        root / "site" / "src" / "content" / "docs",
    )

    _write(root / "docs/specs/F-0001-example.md", _spec())
    _write(root / "docs/plans/PLAN-F-0001-example.md", _plan())
    _write(
        root / "docs/adr/ADR-0001-example.md",
        """---
title: "ADR-0001: Example"
status: accepted
date: 2026-08-27
---

# ADR-0001: Example
""",
    )
    _write(
        root / "docs/specs/README.md",
        "- [F-0001: Example](F-0001-example.md) — implemented\n",
    )
    _write(
        root / "docs/plans/README.md",
        """## 当前计划

- 无。

## 已完成计划

- [PLAN-F-0001: Example](PLAN-F-0001-example.md)
""",
    )
    _write(
        root / "docs/adr/README.md",
        "- [ADR-0001: Example](ADR-0001-example.md)\n",
    )
    _write(
        root / "site/src/content/docs/example.md",
        """---
title: Example
bearStatus: implemented
sourceRefs:
  - F-0001
  - PLAN-F-0001
  - ADR-0001
---

# Example
""",
    )


def test_governance_accepts_consistent_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_repository(monkeypatch, tmp_path)

    assert check_governance.governance_errors() == []


def test_implemented_feature_cannot_keep_unchecked_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_repository(monkeypatch, tmp_path)
    _write(
        tmp_path / "docs/specs/F-0001-example.md",
        _spec(checklist="- [ ] Docs not reviewed"),
    )

    assert check_governance.governance_errors() == [
        "docs/specs/F-0001-example.md: implemented Feature contains unchecked items"
    ]


def test_index_status_must_match_feature_front_matter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_repository(monkeypatch, tmp_path)
    _write(
        tmp_path / "docs/specs/README.md",
        "- [F-0001: Example](F-0001-example.md) — accepted\n",
    )

    assert check_governance.governance_errors() == [
        "docs/specs/README.md: F-0001 says accepted, Front Matter says implemented"
    ]


def test_implemented_feature_rejects_temporary_branch_as_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_repository(monkeypatch, tmp_path)
    _write(
        tmp_path / "docs/specs/F-0001-example.md",
        _spec(implemented_in="codex/F-0001-example"),
    )

    assert check_governance.governance_errors() == [
        "docs/specs/F-0001-example.md: implemented_in must name a PR or commit"
    ]


def test_plan_state_must_follow_feature_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_repository(monkeypatch, tmp_path)
    _write(tmp_path / "docs/plans/PLAN-F-0001-example.md", _plan(status="active"))
    _write(
        tmp_path / "docs/plans/README.md",
        """## 当前计划

- [PLAN-F-0001: Example](PLAN-F-0001-example.md)

## 已完成计划
""",
    )

    errors = check_governance.governance_errors()

    assert (
        "docs/plans/PLAN-F-0001-example.md: active Plan requires accepted Feature F-0001" in errors
    )
    assert (
        "docs/specs/F-0001-example.md: implemented Feature has unfinished Plan PLAN-F-0001"
        in errors
    )


def test_internal_site_source_ref_must_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_repository(monkeypatch, tmp_path)
    _write(
        tmp_path / "site/src/content/docs/example.md",
        """---
title: Example
bearStatus: mixed
sourceRefs:
  - F-9999
  - external-paper
---

# Example
""",
    )

    assert check_governance.governance_errors() == [
        "site/src/content/docs/example.md: unknown sourceRef F-9999"
    ]


def test_accepted_s2_feature_requires_active_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_repository(monkeypatch, tmp_path)
    _write(
        tmp_path / "docs/specs/F-0001-example.md",
        _spec(status="accepted", change_level="S2"),
    )
    _write(tmp_path / "docs/plans/PLAN-F-0001-example.md", _plan(status="draft"))
    _write(
        tmp_path / "docs/specs/README.md",
        "- [F-0001: Example](F-0001-example.md) — accepted\n",
    )
    _write(
        tmp_path / "docs/plans/README.md",
        """## 当前计划

- [PLAN-F-0001: Example](PLAN-F-0001-example.md)

## 已完成计划
""",
    )

    assert check_governance.governance_errors() == [
        "docs/specs/F-0001-example.md: S2 Feature requires Plan status active"
    ]


def test_index_cannot_register_unknown_feature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_repository(monkeypatch, tmp_path)
    _write(
        tmp_path / "docs/specs/README.md",
        """- [F-0001: Example](F-0001-example.md) — implemented
- [F-9999: Missing](F-0001-example.md) — accepted
""",
    )

    assert check_governance.governance_errors() == [
        "docs/specs/README.md: unknown index entry F-9999"
    ]


def test_draft_feature_may_link_proposed_adr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_repository(monkeypatch, tmp_path)
    _write(tmp_path / "docs/specs/F-0001-example.md", _spec(status="draft"))
    _write(tmp_path / "docs/plans/PLAN-F-0001-example.md", _plan(status="draft"))
    _write(
        tmp_path / "docs/adr/ADR-0001-example.md",
        """---
title: "ADR-0001: Example"
status: proposed
date: 2026-08-27
---

# ADR-0001: Example
""",
    )
    _write(
        tmp_path / "docs/specs/README.md",
        "- [F-0001: Example](F-0001-example.md) — draft\n",
    )
    _write(
        tmp_path / "docs/plans/README.md",
        """## 当前计划

- [PLAN-F-0001: Example](PLAN-F-0001-example.md)

## 已完成计划
""",
    )

    assert check_governance.governance_errors() == []
