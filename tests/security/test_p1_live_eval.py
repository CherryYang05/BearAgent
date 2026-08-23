from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_p1_live_eval import prepare

import bearagent.evaluation.p1_live as p1_live
from bearagent.domain.errors import ErrorCode
from bearagent.evaluation.p1_live import LiveEvalError


def test_prepared_live_plan_repr_does_not_expose_selected_api_key(tmp_path: Path) -> None:
    plan = prepare(tmp_path)

    assert "test-secret" not in repr(plan)
    assert "test-secret" in plan.forbidden_report_values


@pytest.mark.parametrize(
    ("report_json", "forbidden_values", "canary"),
    [
        ('{"value":"selected-secret"}', ("selected-secret",), "safe-canary"),
        ('{"value":"https://provider.test/v1"}', ("https://provider.test/v1",), "safe-canary"),
        ('{"value":"authorization"}', (), "safe-canary"),
        ('{"value":"security-canary"}', (), "security-canary"),
    ],
)
def test_live_report_sanitizer_rejects_sensitive_values(
    report_json: str,
    forbidden_values: tuple[str, ...],
    canary: str,
) -> None:
    with pytest.raises(LiveEvalError) as caught:
        p1_live._assert_sanitized_report(  # pyright: ignore[reportPrivateUsage]
            report_json,
            forbidden_values,
            canary=canary,
        )

    assert caught.value.info.code is ErrorCode.INTERNAL_ERROR
    assert "selected-secret" not in caught.value.info.model_dump_json()
    assert "https://provider.test/v1" not in caught.value.info.model_dump_json()


def test_preflight_does_not_enter_production_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("preflight entered production runtime")

    monkeypatch.setattr(
        p1_live,
        "build_run_services",
        fail_if_called,
    )

    plan = prepare(tmp_path)

    assert plan.preflight.commit == "abc1234"
