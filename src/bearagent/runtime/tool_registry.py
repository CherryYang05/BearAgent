"""Immutable registry of trusted Tool implementations."""

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from bearagent.domain.tools import ToolSpec
from bearagent.ports.tools import Tool


class ToolRegistry:
    """Snapshot registered Tools and resolve them by exact name."""

    def __init__(self, tools: Iterable[Tool]) -> None:
        by_name: dict[str, Tool] = {}
        specs_by_name: dict[str, ToolSpec] = {}
        for tool in tools:
            name = tool.spec.name
            if name in by_name:
                raise ValueError(f"duplicate Tool name: {name}")
            by_name[name] = tool
            specs_by_name[name] = tool.spec
        self._tools: Mapping[str, Tool] = MappingProxyType(by_name)
        self._specs_by_name: Mapping[str, ToolSpec] = MappingProxyType(specs_by_name)
        self._specs = tuple(specs_by_name[name] for name in sorted(specs_by_name))

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        """Return trusted Tool definitions in stable name order."""
        return self._specs

    def get(self, name: str) -> Tool | None:
        """Return the exact registered Tool, without aliases or fallback."""
        return self._tools.get(name)

    def get_spec(self, name: str) -> ToolSpec | None:
        """Return the immutable registration-time Tool definition."""
        return self._specs_by_name.get(name)
