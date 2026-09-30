---
title: F-0002：修改状态和预算规则
description: 具体 Event、Reducer、预算检查的调用关系、修改顺序和测试入口。
bearStatus: implemented
sourceRefs:
  - F-0022
  - ADR-0021
  - F-0002
  - F-0018
  - ADR-0009
  - ADR-0016
  - domain schema snapshot
---

F-0002 把状态计算集中在一处。数据库保存 Event，F-0016 Agent Loop 决定何时请求下一次调用，
F-0005 CLI 显示状态；三者都必须使用这里的规则，不能各自维护一套计数和状态转换。

## 从一条 Event 追代码

```text
domain/run_events.py   声明 Event 携带的数据
        ↓
runtime/reducer.py     检查顺序和状态转换，返回新 RunState
        ↓
runtime/budgets.py     在新的模型或工具请求前检查剩余预算
        ↓
domain/schema.py       把公开数据结构加入兼容性快照
```

状态本身定义在 `domain/runs.py`。Reducer 不访问数据库，也不调用 Provider 或 Tool。

## 每条 Event 会经过哪些检查

1. 根据 `event_type` 和 `schema_version` 找到精确 payload 类型；
2. 确认首条 Event、Run ID 和连续 sequence；
3. 对 v2-shaped Tool terminal evidence，确认完整 execution 使用的原始请求与同版本 requested Event 相同；
4. 确认当前 Run/Activity 允许这个转换，并且 ID 没有重复；
5. 如果是新的模型或工具请求，先检查预算；
6. 创建新的冻结状态，旧状态保持不变。

未知类型、未知版本、sequence 缺口、跨 Run 和非法转换都会被拒绝。公开错误只保留稳定 code、
message 和安全详情，Pydantic 的原始校验文本只作为 Python 异常原因保留。

## 增加或修改 Event 时

- 如果 Event 会改变 P1 状态，同时修改 payload、registry、Reducer、测试和 schema 快照；
- 不兼容的 payload 使用新版本，不要直接改变 v1 的含义；
- 新版本如果复用已有 payload shape，跨 Event 校验应按解析后的类型生效，不要维护容易漏项的版本号清单；
- 模型完成或失败时，保留 Provider 已报告的实际 token 和费用，即使已经超限；
- 模型和工具数据不能提高 `RunCreated` 中的限制；
- F-0022 的 Attempt 使用独立 v5 状态；pause、cancel、`UNKNOWN` 和 Approval 仍待后续交付。

## 验证

```powershell
uv run pytest tests/unit/test_run_reducer.py tests/unit/test_budgets.py
uv run pytest tests/security/test_run_events.py tests/contract/test_domain_schemas.py
uv run python scripts/generate_domain_schemas.py
uv run ruff check .
uv run pyright
```

生成快照后先审查 diff，再运行完整测试。F-0002 自身没有实现 Event store、Agent Loop、真实模型
调用、工具执行或启动恢复；后续 F-0003 至 F-0016 已接通其中一部分，启动恢复仍属于 P2。

## v5 在 Attempt 边界记账

`runtime/attempt_reducer.py` 接收 v5 Event，逻辑 Run/Activity 转换继续复用原 Reducer。
AttemptRequested 增加一次调用次数，AttemptSucceeded/Failed 增加已知用量；逻辑 terminal 校验结果
hash，不重复计费。重试决定必须引用已提交失败，第二次请求只能消费一次决定。

v1-v4 继续按原 Activity Event 计数并使用 state hash format v1。v5 使用 RunStateV5 与 hash format v2；
比较时必须先看格式版本。公开 schema 新增联合分支和错误码，不给旧 RunState 补默认字段。
对应测试见 `tests/security/test_attempt_events.py` 和 `tests/contract/test_attempt_store_contract.py`。
