"""Shared configuration for provider-neutral domain schemas."""

from collections.abc import Mapping
from math import isfinite
from types import MappingProxyType
from typing import cast

from pydantic import BaseModel, ConfigDict, JsonValue

MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 10_000
MAX_EMBEDDED_JSON_NODES = 9_000


class DomainModel(BaseModel):
    """Immutable schema that rejects undeclared boundary data."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


def validate_json_object(
    value: object,
    *,
    max_nodes: int = MAX_JSON_NODES,
) -> dict[str, object]:
    """Validate an ordinary JSON object with bounded depth and node count."""
    if not isinstance(value, Mapping):
        raise ValueError("value must be a JSON object")
    materialized = dict(cast(Mapping[object, object], value))
    _validate_json_value(materialized, max_nodes=max_nodes)
    return cast(dict[str, object], materialized)


def _validate_json_value(
    value: object,
    *,
    depth: int = 0,
    nodes: list[int] | None = None,
    max_nodes: int = MAX_JSON_NODES,
) -> None:
    if nodes is None:
        nodes = [0]
    nodes[0] += 1
    if nodes[0] > max_nodes:
        raise ValueError("JSON value exceeds the node limit")
    if depth > MAX_JSON_DEPTH:
        raise ValueError("JSON value exceeds the nesting limit")

    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return
    if isinstance(value, list):
        for item in cast(list[object], value):
            _validate_json_value(item, depth=depth + 1, nodes=nodes, max_nodes=max_nodes)
        return
    if isinstance(value, dict):
        for key, item in cast(dict[object, object], value).items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            _validate_json_value(item, depth=depth + 1, nodes=nodes, max_nodes=max_nodes)
        return
    raise ValueError(f"JSON contains unsupported value: {type(value).__name__}")


def freeze_json_mapping(value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    """Copy JSON data into recursively read-only containers."""
    return MappingProxyType({key: _freeze_json_value(item) for key, item in value.items()})


def _freeze_json_value(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return cast(JsonValue, freeze_json_mapping(value))
    if isinstance(value, list):
        return cast(JsonValue, tuple(_freeze_json_value(item) for item in value))
    return value


def thaw_json_mapping(value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """Convert read-only JSON containers back to ordinary serialization values."""
    return {key: _thaw_json_value(item) for key, item in value.items()}


def _thaw_json_value(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        mapping = cast(Mapping[str, object], value)
        return {key: _thaw_json_value(item) for key, item in mapping.items()}
    if isinstance(value, tuple):
        return [_thaw_json_value(item) for item in cast(tuple[object, ...], value)]
    return cast(JsonValue, value)
