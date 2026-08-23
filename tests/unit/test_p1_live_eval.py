import json
from pathlib import Path

import pytest
from tests.agent_loop_fixtures import agent_settings, budget_limits

from bearagent.domain.agent import ModelPricing, RunProfileV2
from bearagent.domain.errors import ErrorCode
from bearagent.evaluation.p1_live import LiveEvalError, prepare_live_eval

REPOSITORY_ROOT = Path(__file__).parents[2]
EVAL_ROOT = REPOSITORY_ROOT / "evals" / "p1"


def write_live_configuration(tmp_path: Path, *, include_api_key: bool = True) -> tuple[Path, Path]:
    config = agent_settings().model_copy(
        update={
            "tool_names": (
                "workspace.list",
                "workspace.read",
                "workspace.search",
                "workspace.write",
            )
        }
    )
    profile = RunProfileV2(
        provider_id="primary",
        agent_config=config,
        budget_limits=budget_limits(max_tool_calls=10),
    )
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(profile.model_dump_json(indent=2) + "\n", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "providers": [
                    {
                        "provider_id": "primary",
                        "name": "Example AI",
                        "protocol": "openai_chat_completions",
                        "base_url": "https://provider.test/v1",
                        **({"api_key": "test-secret"} if include_api_key else {}),
                        "models": [
                            {
                                "model_id": "test-model",
                                "name": "Test Model",
                            }
                        ],
                        "default_model": "test-model",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return profile_path, config_path


def prepare(
    tmp_path: Path,
    *,
    allow_live_api: bool = True,
    cap: int = 500_000,
    include_api_key: bool = True,
):
    profile_path, config_path = write_live_configuration(tmp_path, include_api_key=include_api_key)
    return prepare_live_eval(
        profile_path=profile_path,
        config_path=config_path,
        suite_path=EVAL_ROOT / "tasks.json",
        eval_root=EVAL_ROOT,
        allow_live_api=allow_live_api,
        expected_provider_id="primary",
        expected_model="test-model",
        pricing=ModelPricing(
            version="pricing-v1",
            input_microusd_per_million_tokens=2_000_000,
            output_microusd_per_million_tokens=8_000_000,
        ),
        commit="abc1234",
        authorized_cost_cap_microusd=cap,
    )


def test_preflight_succeeds_with_only_sanitized_runtime_estimate(tmp_path: Path) -> None:
    plan = prepare(tmp_path)

    assert plan.preflight.suite_version == "1.1.1"
    assert plan.preflight.commit == "abc1234"
    assert plan.preflight.task_ids == (
        "single-document-intro",
        "multi-document-summary",
        "source-comparison",
        "replace-existing-output",
        "path-denied-low-budget",
    )
    assert plan.preflight.runtime_estimated_max_cost_microusd == 400_000
    dumped = plan.preflight.model_dump_json()
    assert "test-secret" not in dumped
    assert "https://provider.test/v1" not in dumped


@pytest.mark.parametrize(
    ("allow_live_api", "cap", "include_api_key", "expected_code"),
    [
        (False, 500_000, True, ErrorCode.INVALID_INPUT),
        (True, 500_000, False, ErrorCode.INVALID_INPUT),
        (True, 399_999, True, ErrorCode.BUDGET_EXHAUSTED),
    ],
)
def test_preflight_failure_creates_no_attempt_files(
    tmp_path: Path,
    allow_live_api: bool,
    cap: int,
    include_api_key: bool,
    expected_code: ErrorCode,
) -> None:
    evidence_root = tmp_path / "must-not-exist"

    with pytest.raises(LiveEvalError) as caught:
        prepare(
            tmp_path,
            allow_live_api=allow_live_api,
            cap=cap,
            include_api_key=include_api_key,
        )

    assert caught.value.info.code is expected_code
    assert not evidence_root.exists()


def test_preflight_rejects_confirmation_mismatch_before_attempt(tmp_path: Path) -> None:
    profile_path, config_path = write_live_configuration(tmp_path)

    with pytest.raises(LiveEvalError) as caught:
        prepare_live_eval(
            profile_path=profile_path,
            config_path=config_path,
            suite_path=EVAL_ROOT / "tasks.json",
            eval_root=EVAL_ROOT,
            allow_live_api=True,
            expected_provider_id="primary",
            expected_model="different-model",
            pricing=ModelPricing(
                version="pricing-v1",
                input_microusd_per_million_tokens=2_000_000,
                output_microusd_per_million_tokens=8_000_000,
            ),
            commit="abc1234",
            authorized_cost_cap_microusd=500_000,
        )

    assert caught.value.info.code is ErrorCode.INVALID_INPUT
