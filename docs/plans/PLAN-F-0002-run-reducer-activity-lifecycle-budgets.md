---
title: "Implementation Plan: Run reducer, Activity lifecycle and budgets"
status: completed
plan_id: PLAN-F-0002
related_spec: F-0002
created: 2026-08-11
last_updated: 2026-08-13
---

# PLAN-F-0002：Run/Activity 状态和预算

关联 Spec：`docs/specs/F-0002-run-reducer-activity-lifecycle-budgets.md`

## 开始前确认

F-0002 与 ADR-0009 已接受，没有开放问题，也没有其他 active 主 Plan。条件于 2026-08-11 满足。

## 实施步骤

### 第 1 步：能从 Run Event 算出 Run 状态

- 状态：completed；
- 交付结果：Run、预算状态，以及 RunCreated/Started/Succeeded/Failed payload；
- 代码落点：`domain/runs.py`、`domain/run_events.py`、`runtime/reducer.py` 和 schema registry；
- 接入关系：调用方按 sequence 传入 Event，Reducer 返回冻结 RunState；
- 重点测试：创建、启动、终态、非法 sequence、冻结和 JSON 往返；
- 验证：`uv run pytest tests/unit/test_run_reducer.py tests/contract/test_domain_schemas.py`；
- 回退：删除新增 Run 类型和 payload，恢复快照，无持久数据。

### 第 2 步：在 Run 中跟踪模型和 Tool Activity

- 状态：completed；
- 交付结果：两类 Activity 的 request/start/completed/failed Event 和转换；
- 代码落点：Activity state、具体 payload 和 Reducer 分支；
- 接入关系：Agent Loop 将来追加 Event，Store 保存，CLI 直接读取 Reducer 结果；
- 重点测试：全部转换、一个 active Activity、ID 唯一、跨 Run/未知 Event 拒绝和确定性重放；
- 验证：`uv run pytest tests/unit/test_run_reducer.py tests/security/test_run_events.py`；
- 回退：保留 Run 基础状态，删除 Activity payload 和 Reducer 分支。

### 第 3 步：在新 Activity 前检查五类预算

- 状态：completed；
- 交付结果：预算上限/用量、BudgetExhaustion 和稳定 Error；
- 代码落点：`runtime/budgets.py`，Reducer 的 Activity request 路径复用同一检查；
- 接入关系：候选 request 先检查预算，允许后才成为 Event；模型结果返回时记录实际 usage；
- 重点测试：零值、边界、候选次数、全局 token/费用/deadline、失败 usage 和实际超额；
- 验证：`uv run pytest tests/unit/test_budgets.py tests/unit/test_run_reducer.py`；
- 回退：在 F-0002 实现当时可移除预算检查和记账，因为 F-0003/F-0004 尚未开始依赖这些契约。

### 第 4 步：更新快照、文档并关闭 Feature

- 状态：completed；
- 交付结果：最终 schema 快照、exports、学习说明、开发者导读和状态页；
- 代码落点：schema snapshot、`docs/` 与 `site/`；
- 接入关系：未来 Store、Loop 和 CLI 都引用这套状态规则；
- 重点测试：完整 DoD、链接和站点构建；
- 验证：最终验证命令；
- 回退：F-0003 前整体回退，无 migration。

## 每一步都检查过

- [x] 只提供 Event 重放，不声称启动恢复；
- [x] 预算上限只来自受信 RunCreated，未知 Event 和 payload 被拒绝；
- [x] 实现 deadline 检查，不提前实现 cancel；
- [x] State 暴露 sequence、Activity 状态和预算用量，不引入 trace backend；
- [x] F-0003 前无 migration，不兼容 payload 以后使用新版本；
- [x] 工程文档、学习页、开发者页和状态页同步。

## 最终验证

```powershell
$env:UV_CACHE_DIR = 'D:\BearAgent\.uv-cache'
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv run python scripts/check_docs.py
npm run build --prefix=site
git diff --check
```

2026-08-11：62 tests passed，全部质量检查、文档链接、站点构建和 diff 检查通过。
