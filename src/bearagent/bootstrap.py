"""Composition root for production BearAgent adapters."""

import asyncio
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import Field, TypeAdapter, ValidationError

from bearagent import package_version
from bearagent.adapters.model import (
    AnthropicMessagesProvider,
    OpenAIChatCompletionsProvider,
    OpenAIResponsesProvider,
)
from bearagent.adapters.sqlite import SqliteEventStore
from bearagent.adapters.tools import build_workspace_tools
from bearagent.application import AgentLoop, RunQueryService
from bearagent.configuration import ProviderCatalog, ProviderConfig
from bearagent.domain.agent import AgentConfig, ModelPricing, RunProfile, RunProfileV2
from bearagent.domain.errors import BearAgentError, ErrorCategory, ErrorCode, ErrorInfo
from bearagent.domain.ids import IdGenerator
from bearagent.domain.providers import ModelProtocol, ProviderSelection
from bearagent.ports.model import ModelProvider
from bearagent.runtime.fingerprints import build_run_fingerprint
from bearagent.runtime.policy import FixedToolPolicy
from bearagent.runtime.tool_executor import ToolExecutor
from bearagent.runtime.tool_registry import ToolRegistry

MAX_RUN_PROFILE_BYTES = 128 * 1_024
_WINDOWS_REPARSE_POINT = 0x400
MAX_PROVIDER_CATALOG_BYTES = 128 * 1_024


_RUN_PROFILE_ADAPTER: TypeAdapter[RunProfile | RunProfileV2] = TypeAdapter(
    Annotated[RunProfile | RunProfileV2, Field(discriminator="schema_version")]
)


class BootstrapError(BearAgentError):
    """A safe failure while validating configuration or assembling adapters."""


@dataclass(frozen=True, slots=True)
class RunServices:
    """Production services sharing one initialized durable EventStore."""

    profile: RunProfile | RunProfileV2
    agent_config: AgentConfig
    agent_loop: AgentLoop
    queries: RunQueryService


def load_run_profile(profile_path: str | os.PathLike[str]) -> RunProfile | RunProfileV2:
    """Load one bounded UTF-8 JSON profile without accepting links or secrets."""
    path = Path(profile_path)
    try:
        raw = _read_bounded_regular_file(path, max_bytes=MAX_RUN_PROFILE_BYTES)
        decoded = json.loads(raw.decode("utf-8"))
        return _RUN_PROFILE_ADAPTER.validate_python(decoded)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as error:
        raise BootstrapError(
            ErrorInfo(
                category=ErrorCategory.VALIDATION,
                code=ErrorCode.INVALID_INPUT,
                message="Run profile is missing or invalid.",
            ),
            cause=error,
        ) from error


def load_provider_catalog(
    catalog_path: str | os.PathLike[str],
) -> ProviderCatalog:
    """Load Provider entries from one bounded UTF-8 BearAgent config."""

    path = Path(catalog_path)
    try:
        raw = _read_bounded_regular_file(path, max_bytes=MAX_PROVIDER_CATALOG_BYTES)
        decoded = json.loads(raw.decode("utf-8"))
        return ProviderCatalog.model_validate(decoded)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as error:
        raise BootstrapError(
            ErrorInfo(
                category=ErrorCategory.VALIDATION,
                code=ErrorCode.INVALID_INPUT,
                message="BearAgent config is missing or invalid.",
            ),
            cause=error,
        ) from error


async def build_run_services(
    *,
    profile_path: str | os.PathLike[str],
    config_path: str | os.PathLike[str] = Path("data/config.json"),
    workspace_path: str | os.PathLike[str],
    database_path: str | os.PathLike[str],
    provider_catalog: ProviderCatalog | None = None,
    model_provider: ModelProvider | None = None,
    id_generator: IdGenerator | None = None,
) -> RunServices:
    """Validate inputs, initialize SQLite, and assemble the production Run graph."""
    profile = load_run_profile(profile_path)
    provider_selection, provider_config = _resolve_provider_selection(
        profile,
        config_path=config_path,
        provider_catalog=provider_catalog,
    )
    agent_config = resolve_agent_config(profile, provider_config)
    try:
        available_tools = build_workspace_tools(workspace_path, id_generator=id_generator)
        available_names = {tool.spec.name for tool in available_tools}
        configured_names = set(agent_config.tool_names)
        if not configured_names <= available_names:
            raise ValueError("profile references an unavailable Tool")
        # Only configured Tools enter the registry. Policy still defaults to deny,
        # while the Provider never sees definitions outside this trusted profile.
        registry = ToolRegistry(
            tool for tool in available_tools if tool.spec.name in configured_names
        )
        policy = FixedToolPolicy(agent_config.tool_names)
        executor = ToolExecutor(registry, policy)
        provider = (
            model_provider
            if model_provider is not None
            else _build_selected_model_provider(provider_config)
        )
    except Exception as error:
        raise BootstrapError(
            ErrorInfo(
                category=ErrorCategory.VALIDATION,
                code=ErrorCode.INVALID_INPUT,
                message="Run services could not be configured.",
            ),
            cause=error,
        ) from error

    store = SqliteEventStore(Path(database_path))
    await store.initialize()
    return RunServices(
        profile=profile,
        agent_config=agent_config,
        agent_loop=AgentLoop(
            model_provider=provider,
            event_store=store,
            tool_executor=executor,
            id_generator=id_generator,
            provider_selection=provider_selection,
            run_fingerprint=build_run_fingerprint(
                bearagent_version=package_version(),
                policy=policy.fingerprint,
                tool_specs=registry.specs,
            ),
        ),
        queries=RunQueryService(store),
    )


def resolve_agent_config(
    profile: RunProfile | RunProfileV2,
    provider_config: ProviderConfig | None,
) -> AgentConfig:
    if isinstance(profile, RunProfile):
        return profile.agent_config
    if provider_config is None:
        raise AssertionError("RunProfile v2 requires a selected ProviderConfig")

    model_config = provider_config.default_model_config
    return AgentConfig.model_validate(
        {
            **profile.agent_config.model_dump(mode="python"),
            "model": model_config.model_id,
            "pricing": ModelPricing(
                version="unpriced",
                input_microusd_per_million_tokens=0,
                output_microusd_per_million_tokens=0,
            ),
        }
    )


def build_model_provider(provider_config: ProviderConfig) -> ModelProvider:
    """Create exactly the configured protocol adapter without probing or fallback."""

    api_key = provider_config.api_key.get_secret_value()
    if provider_config.protocol is ModelProtocol.OPENAI_RESPONSES:
        return OpenAIResponsesProvider(
            api_key=api_key,
            base_url=provider_config.base_url,
        )
    if provider_config.protocol is ModelProtocol.OPENAI_CHAT_COMPLETIONS:
        model_config = provider_config.default_model_config
        return OpenAIChatCompletionsProvider(
            api_key=api_key,
            base_url=provider_config.base_url,
            thinking_mode=model_config.thinking_mode,
        )

    if provider_config.protocol is ModelProtocol.ANTHROPIC_MESSAGES:
        return AnthropicMessagesProvider(
            api_key=api_key,
            base_url=provider_config.base_url,
        )
    raise AssertionError("ProviderConfig accepted an unsupported protocol")


def _resolve_provider_selection(
    profile: RunProfile | RunProfileV2,
    *,
    config_path: str | os.PathLike[str],
    provider_catalog: ProviderCatalog | None = None,
) -> tuple[ProviderSelection, ProviderConfig | None]:
    if isinstance(profile, RunProfile):
        return (
            ProviderSelection(
                provider_id="legacy-openai",
                config_version="legacy-v1",
                protocol=ModelProtocol.OPENAI_RESPONSES,
            ),
            None,
        )
    catalog = provider_catalog or load_provider_catalog(config_path)
    try:
        provider_config = catalog.get(profile.provider_id)
    except KeyError as error:
        raise BootstrapError(
            ErrorInfo(
                category=ErrorCategory.VALIDATION,
                code=ErrorCode.INVALID_INPUT,
                message="Run profile references an unknown Provider.",
            ),
            cause=error,
        ) from error
    return (
        ProviderSelection(
            provider_id=provider_config.provider_id,
            config_version=provider_config.configuration_version,
            protocol=provider_config.protocol,
        ),
        provider_config,
    )


def _build_selected_model_provider(
    provider_config: ProviderConfig | None,
) -> ModelProvider:
    if provider_config is None:
        return OpenAIResponsesProvider()
    return build_model_provider(provider_config)


async def build_run_query_service(
    database_path: str | os.PathLike[str],
) -> RunQueryService:
    """Open an existing ordinary database without creating a missing one."""
    try:
        path = await asyncio.to_thread(_require_existing_database, database_path)
    except (OSError, ValueError) as error:
        raise BootstrapError(
            ErrorInfo(
                category=ErrorCategory.PERSISTENCE,
                code=ErrorCode.PERSISTENCE_ERROR,
                message="Run database is missing or invalid.",
            ),
            cause=error,
        ) from error

    store = SqliteEventStore(path)
    await store.initialize()
    return RunQueryService(store)


def _is_link_like(path: Path, path_stat: os.stat_result) -> bool:
    if stat.S_ISLNK(path_stat.st_mode):
        return True
    attributes = getattr(path_stat, "st_file_attributes", 0)
    if attributes & _WINDOWS_REPARSE_POINT:
        return True
    try:
        return path.is_junction()
    except OSError:
        return True


def _require_existing_database(database_path: str | os.PathLike[str]) -> Path:
    path = Path(database_path)
    path_stat = path.lstat()
    if _is_link_like(path, path_stat) or not stat.S_ISREG(path_stat.st_mode):
        raise ValueError("database must be an ordinary file")
    return path


def _read_bounded_regular_file(path: Path, *, max_bytes: int) -> bytes:
    initial = path.lstat()
    if _is_link_like(path, initial) or not stat.S_ISREG(initial.st_mode):
        raise ValueError("file must be ordinary")
    if initial.st_size > max_bytes:
        raise ValueError("file exceeds the byte limit")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        opened_before = os.fstat(handle.fileno())
        if not os.path.samestat(initial, opened_before) or not stat.S_ISREG(opened_before.st_mode):
            raise ValueError("file changed during open")
        content = handle.read(max_bytes + 1)
        opened_after = os.fstat(handle.fileno())

    current = path.lstat()
    if (
        len(content) > max_bytes
        or _is_link_like(path, current)
        or not os.path.samestat(opened_before, opened_after)
        or not os.path.samestat(opened_after, current)
        or not _same_file_snapshot(opened_before, opened_after)
    ):
        raise ValueError("file changed while reading")
    return content


def _same_file_snapshot(first: os.stat_result, second: os.stat_result) -> bool:
    return first.st_size == second.st_size and first.st_mtime_ns == second.st_mtime_ns
