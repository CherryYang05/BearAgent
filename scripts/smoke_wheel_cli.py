"""Exercise an installed wheel's Run CLI without reading real Provider credentials."""

import json
import os
import tempfile
from pathlib import Path

from typer.testing import CliRunner

import bearagent.interfaces.cli.main as cli_main
from bearagent.adapters.testing import ScriptedFakeModelProvider
from bearagent.bootstrap import RunServices, build_run_services
from bearagent.domain.agent import AgentConfig, ModelPricing, RunProfile
from bearagent.domain.ids import IdGenerator
from bearagent.domain.model import ModelCompleted, ModelFinishReason, ModelTextDelta, ModelUsage
from bearagent.domain.runs import BudgetLimits
from bearagent.ports.model import ModelProvider


def main() -> None:
    """Run, inspect, and page Events through the installed console application."""
    provider = ScriptedFakeModelProvider(
        [
            (
                ModelTextDelta(text="wheel smoke complete"),
                ModelCompleted(
                    provider_request_id="wheel-smoke-response",
                    model="wheel-smoke-model",
                    finish_reason=ModelFinishReason.STOP,
                    usage=ModelUsage(input_tokens=2, output_tokens=3),
                ),
            )
        ]
    )
    _inject_provider(provider)
    runner = CliRunner()

    with tempfile.TemporaryDirectory(prefix="bearagent-wheel-") as temporary:
        root = Path(temporary)
        profile_path = root / "profile.json"
        database_path = root / "events.db"
        profile = _profile()
        profile_path.write_text(
            json.dumps(profile.model_dump(mode="json")),
            encoding="utf-8",
        )
        run = runner.invoke(
            cli_main.app,
            [
                "run",
                "wheel smoke task",
                "--profile",
                str(profile_path),
                "--workspace",
                str(root),
                "--database",
                str(database_path),
                "--json",
            ],
        )
        if run.exit_code != 0:
            raise RuntimeError("installed wheel Run command failed")
        run_payload = json.loads(run.stdout)
        run_id = run_payload["result"]["run_id"]

        for command in ("inspect", "events"):
            result = runner.invoke(
                cli_main.app,
                ["run", command, run_id, "--database", str(database_path), "--json"],
            )
            if result.exit_code != 0:
                raise RuntimeError(f"installed wheel {command} command failed")
            payload = json.loads(result.stdout)
            if payload["command"] != command:
                raise RuntimeError(f"installed wheel {command} output is invalid")

    print("Installed wheel Run/inspect/events smoke test passed.")


def _inject_provider(provider: ModelProvider) -> None:
    async def build_with_fake(
        *,
        profile_path: str | os.PathLike[str],
        workspace_path: str | os.PathLike[str],
        database_path: str | os.PathLike[str],
        model_provider: ModelProvider | None = None,
        id_generator: IdGenerator | None = None,
    ) -> RunServices:
        del model_provider
        return await build_run_services(
            profile_path=profile_path,
            workspace_path=workspace_path,
            database_path=database_path,
            model_provider=provider,
            id_generator=id_generator,
        )

    cli_main.build_run_services = build_with_fake


def _profile() -> RunProfile:
    return RunProfile(
        agent_config=AgentConfig(
            agent_id="wheel-smoke-agent",
            agent_version="v1",
            instructions="Return a short offline smoke-test response.",
            model="wheel-smoke-model",
            prompt_version="v1",
            context_version="v1",
            max_output_tokens=128,
            model_timeout_ms=5_000,
            max_context_chars=16_384,
            max_tool_result_bytes=4_096,
            tool_names=(),
            pricing=ModelPricing(
                version="offline-v1",
                input_microusd_per_million_tokens=0,
                output_microusd_per_million_tokens=0,
            ),
        ),
        budget_limits=BudgetLimits(
            max_model_iterations=1,
            max_tokens=128,
            max_cost_microusd=1,
            max_wall_time_ms=10_000,
            max_tool_calls=0,
        ),
    )


if __name__ == "__main__":
    main()
