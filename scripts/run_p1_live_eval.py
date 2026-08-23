"""Run the explicitly authorized P1 live-model gate outside default pytest/CI."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from bearagent.domain.agent import ModelPricing
from bearagent.domain.errors import BearAgentError, ErrorCategory, ErrorCode, ErrorInfo
from bearagent.evaluation.p1_live import execute_live_eval, prepare_live_eval

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run five public P1 fixtures through production model composition. "
            "This command can incur Provider charges."
        )
    )
    parser.add_argument(
        "--allow-live-api",
        action="store_true",
        help="Explicitly authorize real Provider calls for this attempt.",
    )
    parser.add_argument("--expect-provider-id", required=True)
    parser.add_argument("--expect-model", required=True)
    parser.add_argument("--expect-pricing-version", required=True)
    parser.add_argument(
        "--input-microusd-per-million-tokens",
        type=int,
        required=True,
    )
    parser.add_argument(
        "--output-microusd-per-million-tokens",
        type=int,
        required=True,
    )
    parser.add_argument("--commit", required=True, help="Expected 7-40 character Git SHA.")
    parser.add_argument(
        "--max-suite-cost-microusd",
        type=int,
        required=True,
        help="Explicit maximum authorized suite cost in micro-USD.",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "p1-run-profile.json",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "config.json",
    )
    parser.add_argument(
        "--suite",
        type=Path,
        default=REPOSITORY_ROOT / "evals" / "p1" / "tasks.json",
    )
    parser.add_argument(
        "--eval-root",
        type=Path,
        default=REPOSITORY_ROOT / "evals" / "p1",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "live-evals" / "p1",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plan = prepare_live_eval(
            profile_path=args.profile,
            config_path=args.config,
            suite_path=args.suite,
            eval_root=args.eval_root,
            allow_live_api=args.allow_live_api,
            expected_provider_id=args.expect_provider_id,
            expected_model=args.expect_model,
            pricing=ModelPricing(
                version=args.expect_pricing_version,
                input_microusd_per_million_tokens=args.input_microusd_per_million_tokens,
                output_microusd_per_million_tokens=args.output_microusd_per_million_tokens,
            ),
            commit=args.commit,
            authorized_cost_cap_microusd=args.max_suite_cost_microusd,
        )
        print(
            "P1 live preflight (Runtime estimate; no calls made yet): "
            + plan.preflight.model_dump_json(),
            file=sys.stderr,
        )
        outcome = asyncio.run(
            execute_live_eval(
                plan,
                evidence_root=args.evidence_root,
            )
        )
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt):
            raise
        info = _safe_error_info(error)
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": info.model_dump(mode="json"),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            {
                "status": outcome.report.verdict,
                "attempt_id": outcome.report.attempt_id,
                "report_path": str(outcome.report_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if outcome.report.verdict == "passed" else 1


def _safe_error_info(error: BaseException) -> ErrorInfo:
    if isinstance(error, BearAgentError):
        return error.info
    return ErrorInfo(
        category=ErrorCategory.INTERNAL,
        code=ErrorCode.INTERNAL_ERROR,
        message="P1 live evaluation could not be completed.",
        retryable=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
