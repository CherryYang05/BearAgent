import asyncio
import json
import os
from pathlib import Path

import pytest
from tests.agent_loop_fixtures import model_completed

from bearagent.adapters.testing import ScriptedFakeModelProvider
from bearagent.adapters.tools import build_workspace_tools
from bearagent.bootstrap import build_run_services, validate_run_configuration
from bearagent.domain.agent import RunInput
from bearagent.domain.errors import ErrorCode
from bearagent.domain.ids import SessionId, ToolCallId
from bearagent.domain.model import ModelFinishReason, ModelTextDelta, ModelToolCall
from bearagent.domain.tools import ToolRequest, ToolStatus
from bearagent.local_setup import initial_run_profile
from bearagent.runtime.policy import FixedToolPolicy
from bearagent.runtime.tool_executor import ToolExecutor
from bearagent.runtime.tool_registry import ToolRegistry

SENTINEL = "synthetic-runtime-secret-do-not-export"


def executor(root: Path, *, protected_paths: tuple[Path, ...] = ()) -> ToolExecutor:
    registry = ToolRegistry(build_workspace_tools(root, protected_paths=protected_paths))
    return ToolExecutor(registry, FixedToolPolicy(spec.name for spec in registry.specs))


def request(name: str, path: str) -> ToolRequest:
    arguments = {"path": path}
    if name == "workspace.search":
        arguments["query"] = "api_key"
    if name == "workspace.write":
        arguments["content"] = "replacement"
    return ToolRequest(tool_call_id=ToolCallId.new(), name=name, arguments=arguments)


@pytest.mark.parametrize(
    "path", ["data/config.json", "Data/config.json", ".env", ".env.local", ".git/config"]
)
def test_read_and_search_do_not_export_reserved_files(tmp_path: Path, path: str) -> None:
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"api_key": SENTINEL}), encoding="utf-8")
    (tmp_path / "guide.md").write_text("api_key belongs outside input material", encoding="utf-8")
    tools = executor(tmp_path)
    denied = asyncio.run(tools.execute(request("workspace.read", path.replace("/", "\\"))))
    assert denied.error is not None
    assert denied.error.code is ErrorCode.WORKSPACE_PATH_DENIED
    search = asyncio.run(tools.execute(request("workspace.search", ".")))
    assert search.status is ToolStatus.SUCCEEDED
    assert SENTINEL not in search.model_dump_json()
    assert "guide.md" in search.model_dump_json()
    listing = asyncio.run(tools.execute(request("workspace.list", ".")))
    assert '"kind":"blocked"' in listing.model_dump_json()


@pytest.mark.parametrize(
    "operation", ["workspace.read", "workspace.list", "workspace.search", "workspace.write"]
)
def test_custom_runtime_path_cannot_be_accessed_or_overwritten(
    tmp_path: Path, operation: str
) -> None:
    target = tmp_path / "outputs" / "settings.json"
    target.parent.mkdir()
    target.write_text(SENTINEL, encoding="utf-8")
    tools = executor(tmp_path, protected_paths=(target,))
    result = asyncio.run(tools.execute(request(operation, "outputs/./settings.json")))
    assert result.error is not None
    assert result.error.code is ErrorCode.WORKSPACE_PATH_DENIED
    assert target.read_text(encoding="utf-8") == SENTINEL
    assert SENTINEL not in result.model_dump_json()


def test_hard_link_alias_of_secret_is_not_read_or_searched(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    secret = tmp_path / "data" / "config.json"
    secret.write_text(json.dumps({"api_key": SENTINEL}), encoding="utf-8")
    os.link(secret, tmp_path / "innocent.json")
    tools = executor(tmp_path)
    read = asyncio.run(tools.execute(request("workspace.read", "innocent.json")))
    assert read.error is not None and read.error.code is ErrorCode.WORKSPACE_PATH_DENIED
    search = asyncio.run(tools.execute(request("workspace.search", ".")))
    assert SENTINEL not in search.model_dump_json()


@pytest.mark.parametrize("config_path", ["data/config.json", "outputs/provider.json"])
def test_production_composition_keeps_credentials_out_of_events_and_context(
    tmp_path: Path,
    config_path: str,
) -> None:
    config = tmp_path / config_path
    config.parent.mkdir(exist_ok=True)
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "providers": [
                    {
                        "provider_id": "primary",
                        "name": "Test",
                        "protocol": "openai_responses",
                        "base_url": "https://example.invalid/v1",
                        "api_key": SENTINEL,
                        "models": [{"model_id": "test-model"}],
                        "default_model": "test-model",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    profile = tmp_path / "profile.json"
    profile.write_text(initial_run_profile().model_dump_json(), encoding="utf-8")
    (tmp_path / "guide.md").write_text("public input", encoding="utf-8")
    calls = (
        ModelToolCall(
            tool_call_id=ToolCallId.new(),
            provider_call_id="read-config",
            name="workspace.read",
            arguments={"path": config_path},
        ),
        ModelToolCall(
            tool_call_id=ToolCallId.new(),
            provider_call_id="search-root",
            name="workspace.search",
            arguments={"path": ".", "query": "api_key"},
        ),
        ModelToolCall(
            tool_call_id=ToolCallId.new(),
            provider_call_id="read-guide",
            name="workspace.read",
            arguments={"path": "guide.md"},
        ),
    )
    provider = ScriptedFakeModelProvider(
        (
            (*calls, model_completed(ModelFinishReason.TOOL_CALLS)),
            (ModelTextDelta(text="done"), model_completed(ModelFinishReason.STOP)),
        )
    )

    async def exercise() -> None:
        services = await build_run_services(
            profile_path=profile,
            config_path=config,
            workspace_path=tmp_path,
            database_path=tmp_path / "runs.db",
            model_provider=provider,
        )
        result = await services.agent_loop.run(
            RunInput(
                session_id=SessionId.new(),
                objective="Read input safely.",
                agent_config=services.agent_config,
                budget_limits=services.profile.budget_limits,
            )
        )
        facts = await services.queries.events(result.run_id)
        assert SENTINEL not in facts.model_dump_json()
        assert "workspace_path_denied" in facts.model_dump_json()
        assert "public input" in facts.model_dump_json()
        assert all(SENTINEL not in item.model_dump_json() for item in provider.requests)
        configured = validate_run_configuration(
            profile_path=profile,
            config_path=config,
            workspace_path=tmp_path,
            database_path=tmp_path / "runs.db",
        )
        tools = ToolExecutor(
            configured.registry, FixedToolPolicy(configured.agent_config.tool_names)
        )
        for path in ("profile.json", "runs.db", "runs.db-wal", "runs.db-shm", "runs.db-journal"):
            denied = await tools.execute(request("workspace.read", path))
            assert denied.error is not None and denied.error.code is ErrorCode.WORKSPACE_PATH_DENIED

    asyncio.run(exercise())
