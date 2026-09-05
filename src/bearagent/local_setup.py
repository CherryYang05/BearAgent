"""Offline, non-overwriting initialization of trusted local configuration."""

import json
import os
import stat
from pathlib import Path

from bearagent.domain.agent import AgentSettings, RunProfileV2
from bearagent.domain.runs import BudgetLimits

DEFAULT_PROFILE_PATH = Path("data/p1-run-profile.json")
DEFAULT_CONFIG_PATH = Path("data/config.json")
DEFAULT_DATABASE_PATH = Path("data/bearagent.db")
DEFAULT_WORKSPACE_PATH = Path(".")


def initial_run_profile() -> RunProfileV2:
    """Return finite starter settings without changing the zero-budget fixtures."""
    return RunProfileV2(
        provider_id="primary",
        agent_config=AgentSettings(
            agent_id="local-file-agent",
            agent_version="p1-v1",
            instructions=(
                "Use the workspace Tools to read source material. "
                "Write requested results below outputs/. Local runtime files are inaccessible."
            ),
            prompt_version="p1-v1",
            context_version="p1-v1",
            max_output_tokens=1024,
            model_timeout_ms=30000,
            max_context_chars=65536,
            max_tool_result_bytes=16384,
            tool_names=("workspace.list", "workspace.read", "workspace.search", "workspace.write"),
        ),
        budget_limits=BudgetLimits(
            max_model_iterations=8,
            max_tool_calls=16,
            max_tokens=80000,
            max_wall_time_ms=120000,
            # Required by the existing schema. Unpriced runs cannot measure bills.
            max_cost_microusd=1000000,
        ),
    )


def initialize_local_config() -> tuple[str, ...]:
    """Create missing templates in data/ without reading or replacing existing files."""
    directory = Path("data")
    directory.mkdir(exist_ok=True)
    _require_ordinary(directory, directory=True)
    config = {
        "schema_version": 1,
        "providers": [
            {
                "provider_id": "primary",
                "name": "My model service",
                "protocol": "openai_chat_completions",
                "base_url": "https://example.invalid/v1",
                "api_key": "",
                "models": [{"model_id": "replace-with-model-id"}],
                "default_model": "replace-with-model-id",
            }
        ],
    }
    templates = (
        (directory / ".gitignore", "*\n"),
        (DEFAULT_CONFIG_PATH, json.dumps(config, ensure_ascii=False, indent=2) + "\n"),
        (DEFAULT_PROFILE_PATH, initial_run_profile().model_dump_json(indent=2) + "\n"),
    )
    created: list[str] = []
    for path, content in templates:
        _require_ordinary(directory, directory=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            _require_ordinary(path, directory=False)
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        created.append(path.as_posix())
    return tuple(created)


def _require_ordinary(path: Path, *, directory: bool) -> None:
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or getattr(metadata, "st_file_attributes", 0) & 0x400
        or path.is_junction()
        or (directory and not stat.S_ISDIR(metadata.st_mode))
        or (not directory and not stat.S_ISREG(metadata.st_mode))
    ):
        raise ValueError("Local configuration requires ordinary files and directories.")
