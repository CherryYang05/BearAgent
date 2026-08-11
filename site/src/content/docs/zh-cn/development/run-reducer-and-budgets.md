---
title: F-0002 开发者实现导读
description: Run/Activity 状态、typed Event payload、纯 Reducer 和预算门的代码地图与验证方式。
bearStatus: implemented
sourceRefs:
  - F-0002
  - ADR-0009
  - domain schema snapshot
---

面向初学者的[Run 状态、Reducer 与预算](../learn/runtime-state-and-budgets.md)解释了为什么要把
状态事实和调度决策分开。本页说明 F-0002 的实现入口与修改约束。

## 代码地图

| 范围 | 位置 | 责任 |
|---|---|---|
| 状态契约 | `src/bearagent/domain/runs.py` | Run/Activity status、预算 limit/usage 和冻结 state |
| Event payload | `src/bearagent/domain/run_events.py` | 12 种 v1 payload 与 type/version 白名单 |
| Reducer | `src/bearagent/runtime/reducer.py` | sequence、转换、ID、串行 Activity 和 usage fold |
| Budget gate | `src/bearagent/runtime/budgets.py` | 下一次 Activity 的五维纯预算判断 |
| Schema | `src/bearagent/domain/schema.py` | 公共 model registry |
| 生成入口 | `scripts/generate_domain_schemas.py` | 刷新兼容性 snapshot |

Runtime Core 不依赖 Provider SDK、SQLite、CLI 或 adapter。F-0003 可以把 reducer 结果写入 projection，
F-0004 可以在调度 Activity 前调用 budget gate，但不能复制或放宽这里的规则。

## Event 处理顺序

Reducer 对每个 Event 依次执行：

1. 按 `event_type + schema_version` 选择 exact payload model；
2. 检查首事件、`run_id` 和连续 sequence；
3. 检查 Run/Activity 合法转换、active Activity 和 ID 唯一性；
4. 在 request Event 前调用预算门；
5. 返回新的冻结 state，旧 state 不发生修改。

未知类型/版本、额外 payload 字段、跨 Run、sequence gap 和非法转换均 fail closed。Pydantic 原始
校验文本只作为 Python exception cause，公开错误保留稳定 code/message 和安全 details。

## 修改契约前要检查什么

- 新 Event 是否真的改变 P1 state；如果是，payload、registry、reducer、测试和 snapshot 必须同改；
- 不兼容 payload 是否需要新 schema version/upcaster，而不是原地改变 v1 含义；
- completion/failure 是否记录所有已知实际 usage，即使 Run 已经超预算；
- 模型或 Tool 数据是否可能扩大 `RunCreated` 中的受信 budget limits；
- 新状态是否其实属于 P2 cancel/recovery/`UNKNOWN` 或 P3 Approval，而被提前加入 P1。

## 验证证据

```powershell
$env:UV_CACHE_DIR = 'D:\BearAgent\.uv-cache'
uv run pytest tests/unit/test_run_reducer.py tests/unit/test_budgets.py
uv run pytest tests/security/test_run_events.py tests/contract/test_domain_schemas.py
uv run python scripts/generate_domain_schemas.py
uv run ruff check .
uv run pyright
```

生成 snapshot 后必须审查 diff，再运行完整测试。F-0002 不包含 Store、Agent Loop、真实模型调用、
Tool 执行、CLI Run 或启动恢复。
