---
title: "Implementation Plan: EventStore contract, SQLite adapter and projections"
status: completed
plan_id: PLAN-F-0003
related_spec: F-0003
created: 2026-08-12
last_updated: 2026-08-12
---

# Implementation Plan: EventStore contract, SQLite adapter and projections

Related Spec: `docs/specs/F-0003-event-store-sqlite-projections.md`

## Preconditions

- F-0003 status is `accepted`.
- ADR-0003 status is `accepted` and contains executable transaction/migration boundaries.
- F-0003 open questions are resolved.
- No other main Implementation Plan is `active`.

所有前置条件已于 2026-08-12 满足。

## Vertical slices

### Slice 1: Store port and shared contract behavior

- Status：completed。
- Domain/contracts：append 返回 RunState；bounded Event query；Run projection query；安全 Store errors。
- Adapter/interface：升级 InMemory adapter，建立 SQLite/InMemory 参数化 contract suite。
- Tests：合法 lifecycle、sequence/ID/transition 拒绝、query bounds、projection 等价。
- Verification command：`uv run pytest tests/contract/test_event_store_contract.py tests/unit/test_testing_adapters.py`。
- Rollback point：恢复原两方法 port/InMemory adapter；没有数据库文件或 migration。

### Slice 2: SQLite migration and durable Event log

- Status：completed。
- Domain/contracts：schema v1、migration ledger/version/hash、Event row serialization。
- Adapter/interface：`SqliteEventStore.initialize/append/list_events`，WAL/foreign key/busy timeout。
- Tests：空库/重复初始化、重开持久性、完整 envelope round-trip、version/hash 失败。
- Verification command：`uv run pytest tests/integration/test_sqlite_event_store.py -k "migration or reopen or event"`。
- Rollback point：删除 adapter/migration 与临时测试数据库；main 尚无用户 schema。

### Slice 3: Transactional Run and Activity projections

- Status：completed。
- Domain/contracts：RunState/ActivityState 与 normalized rows 的双向映射；Event max sequence 核对。
- Adapter/interface：同 transaction reducer + Event insert + projection upsert；`get_run`。
- Tests：projection/reducer 等价、并发同 sequence、insert 后 projection failure 回滚、corruption。
- Verification command：`uv run pytest tests/contract/test_event_store_contract.py tests/integration/test_sqlite_event_store.py tests/security/test_sqlite_event_store.py`。
- Rollback point：整体回退 schema v1；不保留只有 Event 没有 projection 的部分实现。

### Slice 4: Documentation and Feature close

- Status：completed。
- Domain/contracts：审查 port、SQL schema、migration 和错误边界无 SQLite/provider 泄漏。
- Adapter/interface：同步 exports/package data；确认 F-0005 只需 port contract。
- Tests：完整 DoD、wheel 内容、docs links 和 Starlight build。
- Verification command：见 Final verification。
- Rollback point：F-0004/F-0005 开始前整体回退 F-0003 与空数据库。

关闭时同步 architecture、Spec/Plan/ADR/index、站点初学者持久化说明、开发者代码地图和当前状态。

## Cross-cutting checks

- [x] Persistence/recovery：证明 commit 后可重开查询与原子 rollback；不声称 startup resume。
- [x] Permission/security：固定 SQL、可信 database path、payload/query bounds、安全 errors。
- [x] Timeout/cancel/resource limits：有限 busy timeout/row limit/payload bytes；记录 thread cancellation 限制。
- [x] Logs/trace/metrics：持久 correlation/causation/type/version；不引入 backend。
- [x] Migration/rollback：空库/重复/未来 version/hash/failure rollback tests。
- [x] Engineering documentation impact
- [x] Site beginner learning path synchronized
- [x] Site developer documentation synchronized
- [x] Site current status / milestone summary synchronized

## Final verification

```powershell
$env:UV_CACHE_DIR = 'D:\BearAgent\.uv-cache'
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
uv run python scripts/check_docs.py
npm run build --prefix=site
uv build
git diff --check
```

Expected observable results：所有命令退出码为 0；SQLite migration SQL 包含在 wheel；contract suite
同时覆盖 InMemory/SQLite；故障注入后 Event/projection 均无部分提交；站点明确 F-0003 只提供
durable inspectable facts，不提供自动恢复。

结果（2026-08-12）：91 tests passed；Ruff、Ruff format、Pyright、uv lock、53 个 Markdown
文件链接、21 页 Starlight build、wheel/sdist 与 `git diff --check` 通过。wheel 已直接验证包含
`bearagent/adapters/sqlite/migrations/0001_initial.sql`。站点构建保留既有 chunk size 与 sitemap
配置警告，不影响静态页面生成。
