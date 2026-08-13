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

## 可单独完成和测试的实现步骤

### 第一步：存储内部接口与共用行为

- Status：completed。
- 内部数据与规则：append 返回 RunState；有上限的 Event 查询；Run 查询视图；安全存储错误。
- 接口与外部实现：升级内存适配器，建立 SQLite/内存版参数化共用接口测试。
- Tests：合法 lifecycle、sequence/ID/transition 拒绝、query bounds、projection 等价。
- Verification command：`uv run pytest tests/contract/test_event_store_contract.py tests/unit/test_testing_adapters.py`。
- 安全回退点：恢复原两方法内部接口和内存适配器；没有数据库文件或数据迁移。

### 第二步：SQLite 数据迁移与持久 Event 日志

- Status：completed。
- 内部数据与规则：数据库格式 v1、迁移记录/版本/校验值、Event 数据行序列化。
- 接口与外部实现：`SqliteEventStore.initialize/append/list_events`，WAL/外键/忙等待超时。
- Tests：空库/重复初始化、重开持久性、完整 envelope round-trip、version/hash 失败。
- Verification command：`uv run pytest tests/integration/test_sqlite_event_store.py -k "migration or reopen or event"`。
- 安全回退点：删除适配器/迁移与临时测试数据库；main 尚无用户数据格式。

### 第三步：同一事务中的 Run 与 Activity 查询视图

- Status：completed。
- 内部数据与规则：RunState/ActivityState 与规范化数据行的双向映射；Event 最大顺序号核对。
- 接口与外部实现：同一事务中完成 reducer、Event 插入和查询视图更新；`get_run`。
- Tests：projection/reducer 等价、并发同 sequence、insert 后 projection failure 回滚、corruption。
- Verification command：`uv run pytest tests/contract/test_event_store_contract.py tests/integration/test_sqlite_event_store.py tests/security/test_sqlite_event_store.py`。
- 安全回退点：整体回退数据库格式 v1；不保留只有 Event 没有查询视图的部分实现。

### 第四步：文档与 Feature 关闭

- Status：completed。
- 内部数据与规则：审查内部接口、SQL 数据格式、迁移和错误边界无 SQLite/模型服务类型泄漏。
- 接口与外部实现：同步导出与安装包数据；确认 F-0005 只需依赖内部接口规则。
- Tests：完整 DoD、wheel 内容、docs links 和 Starlight build。
- Verification command：见 Final verification。
- 安全回退点：F-0004/F-0005 开始前整体回退 F-0003 与空数据库。

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

预期可观察结果：所有命令退出码为 0；SQLite 迁移 SQL 包含在安装包；共用接口测试
同时覆盖内存版/SQLite 版；故障注入后 Event/查询视图均无部分提交；站点明确 F-0003 只提供
durable inspectable facts，不提供自动恢复。

结果（2026-08-12）：91 tests passed；Ruff、Ruff format、Pyright、uv lock、53 个 Markdown
文件链接、21 页 Starlight build、wheel/sdist 与 `git diff --check` 通过。wheel 已直接验证包含
`bearagent/adapters/sqlite/migrations/0001_initial.sql`。站点构建保留既有 chunk size 与 sitemap
配置警告，不影响静态页面生成。
