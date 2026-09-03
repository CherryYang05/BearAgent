"""Port for bounded diagnostics whose loss cannot affect a Run."""

from typing import Protocol

from bearagent.domain.diagnostics import DiagnosticRecord


class DiagnosticSink(Protocol):
    """Accept one already-safe diagnostic record."""

    def emit(self, record: DiagnosticRecord) -> None: ...


def emit_safely(sink: DiagnosticSink, record: DiagnosticRecord) -> None:
    """Keep diagnostics adapter failures outside Runtime behavior."""

    try:
        sink.emit(record)
    except Exception:
        # A diagnostic signal is never a Run fact or a reason to retry work.
        return
