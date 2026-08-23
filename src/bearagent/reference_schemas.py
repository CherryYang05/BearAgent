"""Generated outer-boundary schemas for configuration and P1 evaluation."""

from pydantic import BaseModel

from bearagent.configuration import ProviderCatalog
from bearagent.domain.agent import RunProfile, RunProfileV2
from bearagent.evaluation.p1 import EvalSuite
from bearagent.evaluation.p1_live import LiveEvalReport, LivePreflightReport

PUBLIC_RUNTIME_CONFIGURATION_MODELS: tuple[type[BaseModel], ...] = (
    EvalSuite,
    LiveEvalReport,
    LivePreflightReport,
    ProviderCatalog,
    RunProfile,
    RunProfileV2,
)


def public_runtime_configuration_schemas() -> dict[str, dict[str, object]]:
    return {
        model.__name__: model.model_json_schema(mode="serialization")
        for model in sorted(
            PUBLIC_RUNTIME_CONFIGURATION_MODELS,
            key=lambda item: item.__name__,
        )
    }
