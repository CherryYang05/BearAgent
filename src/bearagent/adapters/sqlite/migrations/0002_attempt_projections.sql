CREATE TABLE run_attempt_projections (
    run_id TEXT PRIMARY KEY NOT NULL,
    state_json TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES run_projections (run_id) ON DELETE CASCADE
);
