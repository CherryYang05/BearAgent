"""Framework-independent contracts implemented by BearAgent adapters."""

from bearagent.ports.model import ModelProvider, ModelProviderError
from bearagent.ports.store import (
    EventStore,
    EventStoreConflictError,
    EventStoreCorruptionError,
    EventStoreError,
    EventStoreMigrationError,
    EventStoreNotInitializedError,
)
from bearagent.ports.tools import Tool

__all__ = [
    "EventStore",
    "EventStoreConflictError",
    "EventStoreCorruptionError",
    "EventStoreError",
    "EventStoreMigrationError",
    "EventStoreNotInitializedError",
    "ModelProvider",
    "ModelProviderError",
    "Tool",
]
