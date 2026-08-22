---
title: 沿 Event 读懂状态与预算
description: 从 RunCreated 到 RunSucceeded，理解 Reducer 怎样拒绝非法顺序、生成新状态并在下一次 Activity 前检查预算。
bearStatus: implemented
sourceRefs:
  - F-0002
  - domain schema snapshot
---

Reducer 最适合从一串具体 Event 开始读。下面这段记录表示：Run 建立并启动，模型调用完成，Tool
调用完成，最后 Run 成功。

```text
1 RunCreated
2 RunStarted
3 ModelCallRequested
4 ModelCallStarted
5 ModelCallCompleted
6 ToolCallRequested
7 ToolCallStarted
8 ToolCallCompleted
9 RunSucceeded
```

`runtime/reducer.py` 不执行这些动作。它只回答：给定“之前的状态”和“新发生的事实”，新状态应该
是什么？如果第 7 条直接出现在第 3 条之后，它会拒绝，而不是猜测中间发生了什么。

## 先看数据定义，再看分派函数

按下面顺序打开文件：

1. `domain/run_events.py`：每种 Event payload 必须携带哪些 ID、用量和错误；
2. `domain/runs.py`：`RunState`、`ActivityState`、预算上限和用量长什么样；
3. `runtime/reducer.py`：Event 顺序怎样改变状态；
4. `runtime/budgets.py`：请求下一次模型或 Tool Activity 前怎样判断是否还有预算。

`reduce_events` 只是循环调用 `reduce_event`。真正的入口是 `reduce_event(state, event)`：首次调用时
`state` 为 `None`，之后每次都传入上次返回的新对象。

## 第一条 Event 为什么只能是 RunCreated

空状态只能接受 sequence 1 的 `RunCreated`。Reducer 用其中的 `session_id` 和 `budget_limits` 建立
`QUEUED` 状态。这样预算在 Run 创建时就固定，后续模型或 Tool 输出不能提高上限。

之后每条 Event 都先经过三个通用检查：

- `run_id` 必须仍是同一个 Run；
- `sequence` 必须等于 `last_sequence + 1`；
- 已经 `SUCCEEDED` 或 `FAILED` 的 Run 不能再接收事实。

检查发生在状态修改之前，所以失败不会留下“改了一半”的 Python 对象。

## Run 和 Activity 是两层状态机

Run 的 P1 状态很少：

```text
QUEUED -> RUNNING -> SUCCEEDED
                  -> FAILED
```

Activity 分模型和 Tool 两种，生命周期相同：

```text
PENDING -> RUNNING -> SUCCEEDED
                   -> FAILED
```

`ModelCallRequested` 或 `ToolCallRequested` 创建 `PENDING` Activity；Started、Completed、Failed 必须
带回完全相同的 `activity_id` 和 call ID。`_matching_activity` 集中检查这些关联，避免每个分支漏掉
一项。

P1 还限制同一时间最多一个 active Activity。`_require_activity_request_ready` 会扫描现有 Activity，
只要还有 `PENDING` 或 `RUNNING`，新的请求就被拒绝。它让执行记录保持串行，也让预算和恢复语义更
容易验证。

## 为什么请求时计次数，完成时计 token 和费用

模型迭代次数和 Tool 次数在 Requested Event 到来时加一，因为请求已经占用一次尝试。token 和费用
必须等 Provider 完成或失败后才知道，所以在 `ModelCallCompleted` 或 `ModelCallFailed` 中累加。

即使一次模型调用最终超出 token 或费用上限，Reducer 仍保存 Provider 报告的实际用量。预算模块
阻止的是“下一次 Activity”，不会篡改已经发生的事实。

| 预算维度 | 何时检查 | 怎样决定是否阻止 |
|---|---|---|
| 模型迭代次数 | 请求模型前 | 当前次数 + 1 是否超过上限 |
| Tool 次数 | 请求 Tool 前 | 当前次数 + 1 是否超过上限 |
| token | 请求任一 Activity 前 | 已记录 token 是否达到上限 |
| 费用 | 请求任一 Activity 前 | 已记录微美元是否达到上限 |
| 总时间 | 请求任一 Activity 前 | Event 时间与 Run 开始时间之差是否达到上限 |

费用用整数微美元保存，避免浮点累计误差。时间检查必须传入带时区的明确时间，纯函数不会偷偷读
系统时钟，因此同一串 Event 在测试和重放时能得到同样结果。

## “纯 Reducer”在代码里具体意味着什么

`reducer.py` 不读取数据库、不调用模型、不执行 Tool，也不获取当前时间。替换状态时，它收集旧值、
覆盖变化字段，再让 Pydantic 重新验证并返回新实例。旧的 `RunState` 和 `ActivityState` 保持不变。

这带来两个实际好处：

1. 内存 EventStore 和 SQLite adapter 可以调用完全相同的状态规则；
2. 测试只要提供同一串 Event，就能精确复现成功或失败，不依赖外部服务。

## 失败时怎样区分“Event 坏了”和“转换不允许”

格式、run_id、sequence、重复 ID 等事实问题返回 `INVALID_EVENT`。状态机不允许的动作，例如在
`QUEUED` 时请求模型，返回 `INVALID_STATE_TRANSITION`。预算耗尽则返回稳定的
`BUDGET_EXHAUSTED`，并指出维度、上限和已消耗量。

原始 Pydantic 异常只作为 Python cause 保留，公开的 `ErrorInfo` 不复制不受信任的 payload。

## 读测试时重点看这些场景

`tests/unit/test_run_reducer.py` 是最完整的状态示例。建议按顺序读：

- 正常 Run 生命周期和 JSON 往返；
- 模型与 Tool Activity 串行完成；
- 模型失败仍保存已报告 usage；
- active Activity 重叠、重复 ID、call ID 不匹配；
- 空流、sequence 缺口、跨 Run、终态后追加；
- 同一 Event 序列两次计算得到相同状态；
- deadline 之后完成已有 Activity，但阻止下一次请求。

`tests/security/test_run_events.py` 进一步尝试让不受信任 payload 提高预算、使用未知版本或非法 Tool
名称。`tests/unit/test_budgets.py` 单独覆盖五种预算的精确边界。

```powershell
uv run pytest tests/unit/test_run_reducer.py tests/unit/test_budgets.py
uv run pytest tests/security/test_run_events.py
uv run pytest tests/contract/test_domain_schemas.py
```

Reducer 已能确定性计算状态，但它本身不保存 Event，也不会在进程启动时决定怎样继续。下一页从
[一次 SQLite append](sqlite-event-store.md)看状态规则怎样与持久化放进同一个 transaction。
