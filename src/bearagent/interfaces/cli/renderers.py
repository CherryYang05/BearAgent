"""Bounded human and JSON rendering for Run CLI results."""

import json

from pydantic import BaseModel

from bearagent.domain.agent import RunResult
from bearagent.domain.errors import ErrorInfo
from bearagent.domain.queries import EventPage, RunInspection

MAX_HUMAN_FINAL_TEXT_CHARS = 50_000
COST_NOTE = "Cost: local accounting only; unpriced runs do not measure or cap Provider billing."


def render_json(value: BaseModel) -> str:
    """Serialize exactly one stable JSON object."""
    return json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def render_run(result: RunResult) -> str:
    """Render one terminal Run without exposing raw adapter data."""
    usage = result.state.budget_usage
    lines = [
        f"Run ID: {result.run_id}",
        f"Status: {result.state.status.value}",
        (
            "Usage: "
            f"models={usage.model_iterations}, tokens={usage.tokens}, "
            f"cost_microusd={usage.cost_microusd}, tools={usage.tool_calls}"
        ),
    ]
    lines.append(COST_NOTE)
    for activity in result.state.activities:
        label = activity.kind.value
        if activity.tool_name is not None:
            label = f"{label}:{activity.tool_name}"
        lines.append(f"Activity: {label} {activity.status.value}")
    for artifact in result.artifacts:
        lines.append(
            f"Artifact: {artifact.path} ({artifact.size_bytes} bytes, sha256={artifact.sha256})"
        )
    if result.final_text is not None:
        lines.extend(("Final text:", _bounded_text(result.final_text)))
    if result.state.terminal_error is not None:
        lines.append(f"Error: {render_error(result.state.terminal_error)}")
    return "\n".join(lines)


def render_inspection(inspection: RunInspection) -> str:
    """Render the complete reducer projection and committed Artifact metadata."""
    state = inspection.state
    usage = state.budget_usage
    lines = [
        f"Run ID: {inspection.run_id}",
        f"Status: {state.status.value}",
        f"Last sequence: {state.last_sequence}",
        (
            "Usage: "
            f"models={usage.model_iterations}, tokens={usage.tokens}, "
            f"cost_microusd={usage.cost_microusd}, tools={usage.tool_calls}"
        ),
    ]
    lines.append(COST_NOTE)
    if inspection.provider_selection is not None:
        selection = inspection.provider_selection
        lines.extend(
            (
                f"Provider ID: {selection.provider_id}",
                f"Provider protocol: {selection.protocol.value}",
                f"Provider config version: {selection.config_version}",
            )
        )
    if inspection.run_fingerprint is not None:
        fingerprint = inspection.run_fingerprint
        lines.extend(
            (
                f"BearAgent version: {fingerprint.bearagent_version}",
                (
                    f"Policy contract: {fingerprint.policy.version} "
                    f"sha256={fingerprint.policy.sha256}"
                ),
            )
        )
        lines.extend(
            f"Tool contract: {tool.name} {tool.spec_version} sha256={tool.sha256}"
            for tool in fingerprint.tools
        )
    for activity in state.activities:
        label = activity.kind.value
        if activity.tool_name is not None:
            label = f"{label}:{activity.tool_name}"
        lines.append(f"Activity: {label} {activity.status.value}")
    for artifact in inspection.artifacts:
        lines.append(
            f"Artifact: {artifact.path} ({artifact.size_bytes} bytes, sha256={artifact.sha256})"
        )
    if state.terminal_error is not None:
        lines.append(f"Error: {render_error(state.terminal_error)}")
    return "\n".join(lines)


def render_events(page: EventPage) -> str:
    """Render one-line Event summaries without printing payloads."""
    lines = [
        f"Run ID: {page.run_id}",
        (
            f"Events after {page.after_sequence}: {len(page.events)} "
            f"(next={page.next_after_sequence}, has_more={str(page.has_more).lower()})"
        ),
    ]
    lines.extend(
        (
            f"{event.sequence} {event.occurred_at.isoformat()} "
            f"{event.event_type} v{event.schema_version}"
        )
        for event in page.events
    )
    return "\n".join(lines)


def render_error(error: ErrorInfo) -> str:
    """Render only normalized safe ErrorInfo fields."""
    retry = " retryable" if error.retryable else ""
    return f"{error.code.value} ({error.category.value}{retry}): {error.message}"


def _bounded_text(value: str) -> str:
    if len(value) <= MAX_HUMAN_FINAL_TEXT_CHARS:
        return value
    return value[:MAX_HUMAN_FINAL_TEXT_CHARS] + "\n[output truncated]"
