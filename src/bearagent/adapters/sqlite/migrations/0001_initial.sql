CREATE TABLE events (
    event_id TEXT PRIMARY KEY NOT NULL CHECK (length(event_id) = 36),
    run_id TEXT NOT NULL CHECK (length(run_id) = 36),
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    event_type TEXT NOT NULL CHECK (length(event_type) BETWEEN 1 AND 128),
    schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
    occurred_at TEXT NOT NULL,
    causation_id TEXT NOT NULL CHECK (length(causation_id) = 36),
    correlation_id TEXT NOT NULL CHECK (length(correlation_id) = 36),
    payload_json TEXT NOT NULL,
    UNIQUE (run_id, sequence)
);

CREATE INDEX events_run_sequence_idx ON events (run_id, sequence);
CREATE INDEX events_correlation_idx ON events (correlation_id);

CREATE TABLE run_projections (
    run_id TEXT PRIMARY KEY NOT NULL CHECK (length(run_id) = 36),
    session_id TEXT NOT NULL CHECK (length(session_id) = 36),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    max_model_iterations INTEGER NOT NULL CHECK (max_model_iterations >= 0),
    max_tokens INTEGER NOT NULL CHECK (max_tokens >= 0),
    max_cost_microusd INTEGER NOT NULL CHECK (max_cost_microusd >= 0),
    max_wall_time_ms INTEGER NOT NULL CHECK (max_wall_time_ms >= 0),
    max_tool_calls INTEGER NOT NULL CHECK (max_tool_calls >= 0),
    model_iterations INTEGER NOT NULL CHECK (model_iterations >= 0),
    input_tokens INTEGER NOT NULL CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL CHECK (output_tokens >= 0),
    cost_microusd INTEGER NOT NULL CHECK (cost_microusd >= 0),
    tool_calls INTEGER NOT NULL CHECK (tool_calls >= 0),
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    terminal_error_json TEXT,
    last_sequence INTEGER NOT NULL CHECK (last_sequence >= 1)
);

CREATE INDEX run_projections_status_idx ON run_projections (status, created_at);

CREATE TABLE activity_projections (
    activity_id TEXT PRIMARY KEY NOT NULL CHECK (length(activity_id) = 36),
    run_id TEXT NOT NULL CHECK (length(run_id) = 36),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    kind TEXT NOT NULL CHECK (kind IN ('model', 'tool')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
    requested_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    error_json TEXT,
    model_call_id TEXT CHECK (model_call_id IS NULL OR length(model_call_id) = 36),
    tool_call_id TEXT CHECK (tool_call_id IS NULL OR length(tool_call_id) = 36),
    tool_name TEXT,
    FOREIGN KEY (run_id) REFERENCES run_projections (run_id) ON DELETE CASCADE,
    UNIQUE (run_id, ordinal),
    CHECK (
        (kind = 'model' AND model_call_id IS NOT NULL AND tool_call_id IS NULL AND tool_name IS NULL)
        OR
        (kind = 'tool' AND model_call_id IS NULL AND tool_call_id IS NOT NULL AND tool_name IS NOT NULL)
    )
);

CREATE INDEX activity_projections_run_ordinal_idx
    ON activity_projections (run_id, ordinal);
