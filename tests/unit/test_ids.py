import json
from uuid import UUID, uuid1

import pytest
from pydantic import ValidationError

from bearagent.domain.ids import EventId, RunId, Uuid4IdGenerator


def test_id_generation_and_json_round_trip() -> None:
    run_id = Uuid4IdGenerator().new(RunId)

    assert UUID(str(run_id)).version == 4
    assert run_id.model_dump(mode="json") == str(run_id)
    assert RunId.model_validate_json(json.dumps(str(run_id))) == run_id


def test_id_types_are_not_interchangeable() -> None:
    run_id = RunId.new()
    event_id = EventId.parse(str(run_id))

    assert run_id != event_id


def test_id_rejects_non_uuid4_and_invalid_text() -> None:
    with pytest.raises(ValidationError, match="UUID version 4"):
        RunId.parse(str(uuid1()))

    with pytest.raises(ValidationError, match="valid UUID"):
        RunId.parse("run-1")
