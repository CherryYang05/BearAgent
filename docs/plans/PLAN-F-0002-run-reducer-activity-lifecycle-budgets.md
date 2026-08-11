---
title: "Implementation Plan: Run reducer, Activity lifecycle and budgets"
status: completed
plan_id: PLAN-F-0002
related_spec: F-0002
created: 2026-08-11
last_updated: 2026-08-11
---

# Implementation Plan: Run reducer, Activity lifecycle and budgets

Related Spec: `docs/specs/F-0002-run-reducer-activity-lifecycle-budgets.md`

## Preconditions

- F-0002 status is `accepted`.
- ADR-0009 status is `accepted`.
- F-0002 open questions remain empty or are resolved in the Spec.
- No other main Implementation Plan is `active`.

所有前置条件已于 2026-08-11 满足；全部切片已完成，仓库恢复为无 `active` 主 Plan。

## Vertical slices

### Slice 1: Run lifecycle and schema baseline

- Status：completed。
- Domain/contracts：Run/budget 状态模型、RunCreated/Started/Succeeded/Failed v1 payload。
- Adapter/interface：公共 schema registry/export；无 adapter I/O。
- Tests：创建、启动、成功/失败、非法 sequence/terminal、冻结与 JSON round-trip。
- Verification command：`uv run pytest tests/unit/test_run_reducer.py tests/contract/test_domain_schemas.py`。
- Rollback point：删除新增 Run 模型和 payload，恢复 schema snapshot；无持久数据。

### Slice 2: Serial Model and Tool Activity lifecycle

- Status：completed。
- Domain/contracts：Activity state、Model/Tool request/start/completed/failed payload 与严格 reducer。
- Adapter/interface：runtime reducer public functions；不接真实 Provider/Tool。
- Tests：两类 Activity 全转换、单 active 约束、ID 唯一性、跨 Run/未知 Event 拒绝和确定性 fold。
- Verification command：`uv run pytest tests/unit/test_run_reducer.py tests/security/test_run_events.py`。
- Rollback point：保留 Slice 1 的 Run lifecycle，移除 Activity payload/reducer 分支。

### Slice 3: Budget gate and usage accounting

- Status：completed。
- Domain/contracts：五类 limit/usage、BudgetExhaustion 与稳定错误码。
- Adapter/interface：纯 `check_activity_budget`；reducer 在 Activity request 使用同一规则。
- Tests：零值/边界/超限、相关次数门槛、全局 token/费用/deadline、失败 usage 与已开始 Activity
  跨 deadline/实际超额。
- Verification command：`uv run pytest tests/unit/test_budgets.py tests/unit/test_run_reducer.py`。
- Rollback point：移除 budget gate 与记账分支；F-0003/F-0004 尚未依赖。

### Slice 4: Documentation and Feature close

- Status：completed。
- Domain/contracts：生成并审查最终 schema snapshot；确认无 Provider/Store 类型泄漏。
- Adapter/interface：domain/runtime exports 与 import boundary 检查。
- Tests：完整 DoD、docs link 和 Starlight build。
- Verification command：见 Final verification。
- Rollback point：在 F-0003 开始前整体回退 F-0002；无 migration。

实现关闭时同步：

- `docs/architecture/overview.md` 的 Event 清单、状态/预算当前事实与 ADR 索引；
- `site/.../learn/` 的 reducer/有界 Runtime 初学者说明；
- `site/.../development/` 的 F-0002 代码地图、失败语义与测试证据；
- `site/.../project/status.md` 的当前实现状态。

## Cross-cutting checks

- [x] Persistence/recovery：只提供 event-only deterministic fold；不声称 startup recovery。
- [x] Permission/security：limits 只来自受信 RunCreated；未知 Event/payload fail closed。
- [x] Timeout/cancel/resource limits：deadline gate 与整数安全上限；不实现 cancel。
- [x] Logs/trace/metrics：state 暴露 sequence、Activity status 与 budget usage；不引入 backend。
- [x] Migration/rollback：F-0003 前无持久 migration；记录 payload v1 后续演进规则。
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
git diff --check
```

Expected observable results：所有命令退出码为 0；schema snapshot 无未提交生成差异；完整测试包含
Run/Activity/reducer/budget/contract/security 覆盖；站点明确区分 F-0002 已实现与 P2/P3 规划能力。

结果（2026-08-11）：62 tests passed；Ruff、Ruff format、Pyright、uv lock、文档链接、Starlight
构建与 `git diff --check` 在最终关闭前验证。
