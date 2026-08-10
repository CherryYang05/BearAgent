# BearAgent repository instructions

## Read before changing code

1. Read `docs/architecture/overview.md`.
2. Read `docs/project/roadmap.md` and `docs/specs/README.md` to identify the current milestone and Feature.
3. Read the accepted Feature Spec, its active Implementation Plan, and related ADRs.
4. Inspect the current code and tests; chat history is never a source of truth.

## Project tracking

- `P0`, `P1`, and later milestones live in `docs/project/roadmap.md`.
- Feature IDs are global and stable. Every Feature Spec must declare `milestone: P<n>`; do not encode the milestone into `F-NNNN` or rename a Feature when it moves.
- Feature Spec and ADR filenames must begin with their full IDs: `F-NNNN-*.md` and `ADR-NNNN-*.md`.
- Feature status lives in the Feature Spec. Slice-level progress lives in `docs/plans/PLAN-F-NNNN-*.md`.
- ADR status records whether a decision is accepted, not whether its implementation is complete.
- Keep at most one Implementation Plan `active`; reconcile its claims with code and tests before continuing it.

## Git branches

- Feature branches created by Codex must use `codex/F-NNNN-<short-slug>`, where `F-NNNN` exactly matches the related Feature Spec ID.
- Use a concise lowercase kebab-case slug that describes the branch scope, for example `codex/F-0003-sqlite-event-store`.
- Keep one primary Feature per branch. If a Feature moves to another milestone, keep its stable Feature ID in the branch name.
- For S0 fixes or documentation work with no Feature Spec, use `codex/fix-<short-slug>` or `codex/docs-<short-slug>`.

## Change classification

- S0, trivial repair: implementation plus a regression test; update public docs only when observable behavior changes.
- S1, feature or behavior change: create or update a feature spec before implementation.
- S2, cross-module architecture, security boundary, persistence schema, public contract, or new production dependency: feature spec plus an ADR and explicit failure/security tests.

Do not create ceremonial documents for formatting-only or mechanical changes.

## Architecture boundaries

- The runtime core must not import FastAPI, UI code, provider SDK response types, MCP clients, Docker clients, or database adapters.
- Internal domain types are the only types allowed across ports. Translate external SDK objects at adapter boundaries.
- Model output and tool output are untrusted data. They cannot grant permissions or bypass policy checks.
- Every external side effect must pass through the tool executor and policy engine.
- Persist facts as events. Treat run tables, activity tables, checkpoints, and search indexes as projections or caches.
- Never claim exactly-once execution. Mutating activities need an idempotency key or an explicit `UNKNOWN` recovery path.
- Keep the first implementation single-user and single-process unless an accepted spec changes that scope.

## Terminology

Use the glossary in `docs/architecture/overview.md`. In particular:

- Session is a conversation container.
- Run is one user-request execution.
- Activity is one model or tool operation.
- Event is an immutable persisted fact.
- Skill is reusable instruction/context.
- Grant is runtime authority.
- Workflow is an optional deterministic multi-stage pipeline.

Do not introduce synonyms such as Task, Job, Thread, Turn, Capability, or Agent Session for these domain concepts without an ADR.

## Implementation rules

- Prefer the standard library and small, explicit dependencies.
- Keep diffs narrow and avoid unrelated refactors.
- Validate input at system boundaries.
- Add timeouts and output-size limits to external calls.
- Never log secrets, raw authorization headers, or full sensitive tool results.
- Do not add shell execution to the host runtime process.

## Definition of done

A change is complete only when:

- acceptance criteria are satisfied;
- relevant unit, contract, integration, recovery, and security tests pass;
- architecture/spec/ADR/user docs are updated when their claims changed;
- the active Implementation Plan is completed or accurately records remaining slices;
- the diff contains no provider type leakage, policy bypass, undocumented schema migration, or secret exposure;
- verification commands and any known limitations are reported.
