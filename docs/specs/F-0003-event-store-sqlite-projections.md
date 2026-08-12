---
title: "Feature: EventStore contract, SQLite adapter and projections"
status: implemented
spec_id: F-0003
milestone: P1
owner: CherryYang05
created: 2026-08-12
last_updated: 2026-08-12
implemented_in: "codex/F-0003-sqlite-event-store"
related_adrs:
  - ADR-0001
  - ADR-0002
  - ADR-0003
  - ADR-0007
  - ADR-0009
---

# Feature: EventStore contract, SQLite adapter and projections

## 1. Background / Problem

F-0001/F-0002 已经定义不可变 Event envelope、typed payload、Run/Activity state 和纯 reducer，
但事实仍只存在于测试内存中。进程退出后，已接受的 Event、预算用量和终态全部丢失；后续
Agent Loop 与 CLI 也没有统一的 append/query 边界。若 Event 与 projection 分开提交，故障可能
留下“状态已更新但事实不存在”或“事实存在但 inspect 看不到”的分叉。

F-0003 建立 P1 的 durable facts 基线：一个无 ORM 的 SQLite adapter 在同一 transaction 内追加
Event 并更新 reducer 派生的 Run/Activity projection。它保证已提交事实可在重开数据库后查询，
但不把“可查询”夸大为 P2 的自动恢复。

## 2. Goals

- G-1：冻结最小、Provider/SQLite 无关的 EventStore append/query contract。
- G-2：使用标准库 SQLite 持久化完整 Event envelope，并保持每个 Run sequence 连续且唯一。
- G-3：在同一 transaction 内由现有 reducer 校验 Event 并更新 Run/Activity projection。
- G-4：提供显式、可校验、可回滚的 schema migration v1。
- G-5：对 sequence/ID 冲突、数据库锁、损坏 projection 和 migration 不兼容提供安全失败。
- G-6：用 contract、integration、failure-injection 和 security tests 证明 durable/atomic 边界。

## 3. Non-goals

- NG-1：不实现 Agent Loop、ModelProvider、Tool executor、Artifact 或 CLI commands。
- NG-2：不实现 Checkpoint、startup scan、resume、retry、cancel、receipt 或 `UNKNOWN`；这些属于 P2。
- NG-3：不实现多进程/多 writer 协调、lease、queue、PostgreSQL 或分布式 transaction。
- NG-4：不提供 Event 删除、原地修改、通用 SQL/ORM repository 或 projection 自动修复。
- NG-5：不逐 token 持久化 stream，也不持久化 secret、原始 SDK 对象或 Python exception。
- NG-6：不增加生产依赖；async port 由标准库 `asyncio.to_thread` 包装短 SQLite 操作。

## 4. Terms and assumptions

- **Committed fact**：Event insert 与对应 projection update 已在同一 SQLite transaction 提交。
- **Projection**：由 Event + reducer 派生、用于查询的 Run/Activity 行；不是独立事实来源。
- **Migration ledger**：记录已应用 schema version、名称和内容 hash 的表。
- P1 使用一个 Runtime 进程；每次 adapter 操作使用独立 connection，SQLite 序列化短写事务。
- 数据库路径来自受信 composition/configuration，不接受模型或 Tool 输出直接选择。
- Event payload 的 canonical JSON UTF-8 表示设置有限上限，避免单条不可信事实无限占用数据库。

## 5. User scenarios

### Scenario A：重开数据库后查询已提交事实

Given 一个已初始化数据库，When 连续 append 合法 Run Events、关闭 adapter 并重新初始化，Then
按 sequence 查询得到值相等的 Event，Run/Activity projection 与 reducer 结果值相等。

### Scenario B：append 与 projection 原子提交

Given projection 写入被故障注入强制失败，When adapter 已执行 Event insert 但 transaction 尚未
提交，Then 整个 transaction 回滚，Event 与 projection 都不存在。

### Scenario C：冲突 writer fail closed

Given 两个调用基于相同 last sequence 同时追加不同 Event，When SQLite 串行化写事务，Then 最多
一个 Event 提交；另一个得到稳定冲突/非法 sequence 失败，不覆盖、不跳号。

### Scenario D：损坏或未来 schema 不被猜测

Given migration hash/version 不兼容或 Event/projection sequence 不一致，When 初始化、读取或 append，
Then adapter 返回安全 persistence failure，不跳过 migration、不合成状态、不宣称 Run 成功。

## 6. Functional requirements

- FR-1：`EventStore.append(event)` 原子追加一个 Event 并返回提交后的 `RunState`。
- FR-2：`list_events(run_id, after_sequence, limit)` 按 sequence 升序返回有界结果；参数有严格范围。
- FR-3：`get_run(run_id)` 返回完整 `RunState` projection 或 `None`；Activity 顺序与 request 顺序一致。
- FR-4：InMemory 与 SQLite adapters 通过同一 contract tests；端口不暴露 connection、row 或 SQL 类型。
- FR-5：append 在写 transaction 内读取当前 projection，核对 Event 最大 sequence，调用 F-0002
  `reduce_event`，插入 Event，并更新 Run 与发生变化的 Activity projection。
- FR-6：首个 Event 必须为 sequence 1 的合法 `RunCreated`；后续 sequence 必须连续。同一
  `event_id` 全库唯一，`run_id + sequence` 唯一。
- FR-7：Event 表保存 envelope 全部字段；payload 使用 deterministic compact JSON UTF-8，读取时
  重新经过 `Event` 和 typed reducer 边界，不信任数据库中的任意 JSON。
- FR-8：Run projection 保存 status、budget limits/usage、时间、terminal error 和 last sequence；
  Activity projection 保存 kind/status/typed IDs、Tool name、时间、error 和稳定 ordinal。
- FR-9：SQLite v1 migration 使用显式 SQL 文件；migration ledger 保存 version/name/SHA-256。
  已应用文件 hash 漂移、未知更高 version 或部分 schema 都必须失败。
- FR-10：初始化设置并验证 `journal_mode=WAL`、`foreign_keys=ON`、有限 `busy_timeout` 和 durable
  synchronous mode；事务使用 `BEGIN IMMEDIATE`，不实现应用层忙等重试。
- FR-11：数据库目录可由受信初始化边界创建；普通 query 不隐式初始化或迁移数据库。
- FR-12：SQLite integrity/locking/I/O/schema 错误转换为不泄漏路径、SQL、payload 或 stack 的
  `EventStoreError`；原有 `RunReducerError` 保留其 validation/budget 语义。
- FR-13：Event payload JSON 超过 4 MiB 时在开启 transaction 前拒绝；query limit 最大 10,000。
- FR-14：取消等待 async append 不承诺停止已经进入 worker thread 的短 SQLite transaction；P1 不把
  这种执行模型称为可取消或可恢复。
- FR-15：adapter 不删除 Event、不更新 Event 行，也不提供绕开 reducer 直接写 projection 的 API。
- FR-16：core 继续不 import SQLite adapter；SQLite adapter 只依赖 domain/runtime/port 和标准库。

## 7. Interfaces

```text
ports.store
  EventStoreError / EventStoreConflictError / EventStoreCorruptionError
  EventStoreMigrationError / EventStoreNotInitializedError
  EventStore.append(Event) -> RunState
  EventStore.list_events(RunId, after_sequence=0, limit=1000) -> tuple[Event, ...]
  EventStore.get_run(RunId) -> RunState | None

adapters.sqlite
  SqliteEventStore(database_path, busy_timeout_ms=5000)
  initialize() -> None
```

F-0005 只通过 port 获取 Event/RunState；不得读取 SQLite 表或复制 projection 逻辑。

## 8. State and data model

SQLite schema v1 包含：

```text
schema_migrations(version, name, checksum, applied_at)
events(event_id PK, run_id, sequence, event_type, schema_version,
       occurred_at, causation_id, correlation_id, payload_json,
       UNIQUE(run_id, sequence))
run_projections(run_id PK, session_id, status, limits..., usage...,
                created_at, started_at, completed_at, terminal_error_json, last_sequence)
activity_projections(activity_id PK, run_id FK, ordinal, kind, status,
                     requested_at, started_at, completed_at, error_json,
                     model_call_id, tool_call_id, tool_name,
                     UNIQUE(run_id, ordinal))
```

Event 是事实来源；projection 可在未来从 Event 重建。F-0003 只维护同步 projection，不提供 rebuild
命令。任何 Event/payload 不兼容变化继续使用 `schema_version`/upcaster；SQLite 列或索引变化使用
递增 migration，不能编辑已发布 migration v1。

## 9. Failure and recovery semantics

- reducer 在 transaction 内拒绝 Event 时，不插入事实或 projection。
- Event insert 后 projection 写失败时 transaction 整体回滚；测试必须直接查询两类表证明。
- lock 超过 `busy_timeout` 后返回 retryable persistence error；adapter 本身不无限重试。
- duplicate event ID 返回稳定 conflict；sequence/transition 错误由 reducer fail closed。
- 读取到无法解析的 JSON、非法 projection 或 Event/projection sequence 分叉时返回 corruption error。
- migration 在独立 `BEGIN IMMEDIATE` transaction 内完成；任一 statement/ledger 写失败则回滚。
- 已成功 commit 的 Event 在正常进程重启后可查询；F-0003 不扫描非终态 Run，也不继续 Activity。
- 不承诺 OS/磁盘损坏零丢失、跨机器复制或 exactly-once 外部副作用。

## 10. Security and privacy

- SQL 只使用固定 statement 和绑定参数；Event 字段不能成为 SQL identifier 或 SQL 文本。
- adapter 错误不包含数据库绝对路径、SQL、payload、authorization data 或原始异常文本。
- payload 先经 Domain JSON 限制，再经 4 MiB 持久化上限；query 数量有界。
- database path 只在 composition boundary 配置；本 Feature 不允许模型、Prompt 或 Tool 改写路径。
- SQLite 文件本身不提供加密或多用户访问控制；P1 是单用户本地边界，secret 不得进入 Event。

## 11. Observability

- 持久 Event 保留 correlation/causation ID、occurred_at、type/version 与 sequence。
- projection 暴露 Run/Activity status、budget usage、safe errors 和 last sequence，供 F-0005 inspect。
- migration ledger 可查询 version/name/checksum/time；不记录机器路径或环境 secret。
- 本 Feature 不引入日志/metric backend，也不在错误中复制完整 Event payload。

## 12. Rollout and rollback

- 当前没有生产数据库；首次初始化从空目录创建 schema v1。
- 在 F-0003 合并前可删除测试数据库并回退代码/migration；没有用户数据迁移。
- schema v1 一旦进入 main，migration 文件视为不可变；后续回退代码必须仍能识别数据库版本，数据
  rollback 通过备份/新 migration，而不是原地改写历史文件。
- database file 与 `-wal`/`-shm` sidecar 是运行数据，不提交 Git。

## 13. Acceptance criteria

- AC-1：两种 adapter 对合法/非法 append、bounded list 和 get_run 通过同一 contract suite。
- AC-2：SQLite 重开后 Event envelope 值相等，projection 与 `reduce_events` 值相等。
- AC-3：sequence gap、重复 event ID、非法 transition 和未知 Event/version 均不产生部分写入。
- AC-4：故障注入使 projection insert/update 失败时，同 transaction 的 Event insert 可证明已回滚。
- AC-5：两个并发 append 竞争同一 sequence 时只提交一个，Event/projection last sequence 一致。
- AC-6：migration v1 从空库成功、重复初始化幂等；未来 version/hash 不兼容稳定失败。
- AC-7：malformed JSON、损坏 projection、超大 payload 和非法 query bounds 安全失败且不泄漏数据。
- AC-8：SQL schema 包含需要的 PK/unique/FK/check constraints 和 Run/Event 查询索引。
- AC-9：重开数据库后非终态 Run 仍显示真实状态，不被标记成功，也不会自动执行任何 Activity。
- AC-10：Ruff、format、Pyright、pytest、docs check、站点 build、wheel package 和 diff check 通过。

## 14. Test plan

- Unit：query bounds、serialization round-trip、error sanitization、projection row/state mapping。
- Contract：InMemory/SQLite 共用 append/list/get_run 行为；port 不泄漏 SQLite 类型。
- Integration：migration、WAL/reopen、完整 lifecycle、normalized projection、并发 writer。
- Recovery：Event insert 后 projection failure 的 transaction rollback；不测试 startup resume。
- Security：SQL-like strings 作为 payload、超大 payload、malformed DB JSON、路径/SQL/内容不进错误。
- Eval/manual：不适用；没有模型或 CLI 行为。

## 15. Documentation impact

- [x] Engineering source of truth (`docs/`)：Spec、扩充 ADR-0003、Plan、架构/索引。
- [x] Site beginner learning path：解释 durable facts、projection 与“持久化不等于恢复”。
- [x] Site developer documentation：代码地图、migration/transaction/失败语义与测试证据。
- [x] Site current status / milestone summary：F-0003 完成状态与仍不支持能力。
- [x] Architecture / ADR：同步 SQLite v1 当前事实与 transaction boundary。
- [x] Deployment docs：无部署入口变化；数据库备份/服务器仍属于后续阶段。
- [x] Generated reference：SQL migration 已进入 wheel；Domain schema 未新增类型且 snapshot 通过。

## 16. Open questions

None. 项目所有者于 2026-08-12 明确启动 F-0003；范围按 Roadmap 与 accepted ADR-0003 固定。
