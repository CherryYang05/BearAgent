---
title: 有界 Agent Loop 与 Run contract identity 实现导读
description: 找到 ContextBuilder、v4 RunCreated、串行协调器、费用估算和 crash observability 测试。
bearStatus: implemented
sourceRefs:
  - F-0016
  - PLAN-F-0016
  - ADR-0013
  - F-0018
  - ADR-0016
  - F-0019
  - ADR-0017
---

阅读 F-0016 时，先跟 `AgentLoop.run(RunInput)`，不要从某个模型或文件 adapter 倒推。Loop 只负责
“下一步接谁”，Context、预算、状态、Policy、模型翻译和文件规则仍各自在原模块中。

```text
EventStore 中的最新事实
  -> check_activity_budget
  -> ContextBuilder.build
  -> ModelCallRequested / Started
  -> ModelProvider.stream
  -> ModelCallCompleted / Failed
  -> ToolCallRequested / Started
  -> ToolExecutor.execute_recorded
  -> ToolCallCompleted / Failed
  -> 下一轮或 RunSucceeded / RunFailed
```

## 代码地图

| 位置 | 责任 |
|---|---|
| `domain/agent.py` | AgentConfig、版本化定价、Context 报告、Run 输入和终态结果 |
| `domain/run_events.py` | v1-v4 payload registry；v4 RunCreated 携带 fingerprint，其余 v4 复用 v2 shape |
| `domain/fingerprints.py` | 有界的 Policy、Tool 与 Run contract identity Value Objects |
| `domain/tools.py` | 原始/规范化请求、Policy 决定、是否到达 adapter 和 ToolResult 的执行记录 |
| `runtime/context.py` | 从已提交的 v2-shaped Activity Event 构造 exact ModelRequest；当前新 Run 使用 schema v4 |
| `runtime/model_stream.py` | 有界组装 text delta、Tool call 和唯一 completion |
| `runtime/pricing.py` | input/output 分别向上取整的整数 micro-USD 估算 |
| `runtime/fingerprints.py` | 对可信注册信息做 canonical JSON + SHA-256，不读取 adapter 状态 |
| `runtime/tool_executor.py` | `execute` 与 `execute_recorded` 汇合到同一个私有执行路径 |
| `application/agent_loop.py` | 保存边界、串行调度、终止和安全失败 |
| `evals/p1/` | 五个版本化任务定义与 workspace fixture |

## v4 RunCreated 怎样复用 v2 Activity 事实

F-0018 以后，新 Run 全部写 schema version 4，SQLite 表结构不变。RunCreated v4 保存目标、预算、
非敏感 AgentConfig、可选 Provider 选择和 `RunFingerprint`。其余 v4 Event 复用 v2 payload shape：
Model requested 保存 exact request 和 Context 报告；Model completed 保存 assistant Message、
Provider request ID、实际模型、finish reason、usage 和费用估算。

`RunFingerprint` 由 bootstrap 使用 package version、`FixedToolPolicy.fingerprint` 与
`ToolRegistry.specs` 构造，再作为 BearAgent domain 类型注入 AgentLoop。Loop 不读取包元数据、文件路径
或具体 Policy 实现，也不再包含“没有 Provider 写 v2、有 Provider 写 v3”的新 Run 分支。旧 v1-v3
parser 永久保留；query 只能从 RunCreated Event 读取 fingerprint，不能用当前 Registry 反推历史。

Tool requested 保存模型提出的原始 ToolRequest。Tool completed/failed 保存可用的
PreparedToolRequest、PolicyDecision、是否真正进入 adapter，以及完整 ToolResult。`workspace.write`
返回的 Artifact 因而随 ToolResult 进入 Event，RunResult 再从这条已校验结果提取元数据。

所有 Event 在进入 Store 前统一受 4 MiB、10,000 个 JSON node 和 32 层限制。exact ModelRequest
放不进 requested Event 时，Provider 不会被调用；模型完成内容放不进 completed Event 时，Run 记录
模型协议失败。若 Tool 已执行但完整执行记录过大，Loop 保存 `persistence_truncated=true` 的有限失败
记录，保留原始请求和 `reached_adapter`，随后终止 Run，不把可能已经发生的副作用自动重试。

Reducer 继续只读取 v1-v4 共有的状态字段，所以 projection schema 不需要 migration。解析 Event 时会
把冻结 JSON 容器还原成普通 JSON，再按事件类型和 schema version 严格校验。

## 五个容易改坏的边界

第一，Provider 和 Tool 只能在 started Event 提交成功后调用。任何 append 失败都原样向上返回；Loop
不会再追加一个“看起来更完整”的失败 Event，因为事实边界本身已经不可信。

第二，ToolExecutor 的两个公共入口只决定返回 `ToolResult` 还是完整执行记录。lookup、输入限制、
prepare、Policy、timeout、adapter 调用和输出检查只存在一份。Agent Loop 不能直接调用具体 Tool。

第三，调用者取消时 `CancelledError` 原样传播。模型或 Tool Activity 可能保持 RUNNING；P1 不
添加恢复、自动 retry 或 `UNKNOWN` 来掩盖这个事实。

第四，同一个版本中的 ToolCallRequested 与 v2-shaped terminal evidence 必须包含值相等的原始
ToolRequest。当前 schema v2、v3、v4 都执行这条检查。Reducer 依据解析后的 payload shape 判断，避免
新增复用相同 shape 的版本时漏掉校验；检查仍只读取 Event 历史，不给 Run/Activity projection 添加
版本专属字段。

第五，`ErrorInfo.retryable` 与 `ToolRetrySafety` 只保留来源观测和 Tool contract 声明。AgentLoop 不根据
它们启动第二次调用。未来的恢复必须建立新的 Attempt 与 RecoveryDecision，不能在当前 Loop 增加隐藏
retry 分支。

## 从哪里看测试

- `tests/unit/test_context_builder.py`：固定层、Tool schema、完整交互组和截断；
- `tests/unit/test_agent_loop.py`：文本结束、多 Tool、Tool 失败、预算和协议失败；
- `tests/recovery/test_agent_loop_boundaries.py`：每个外部调用前后的 append 故障与取消；
- `tests/recovery/test_crash_observability.py`：K1-K6 子进程退出、SQLite 重开、文件 oracle、CLI 与调用次数；
- `tests/security/test_agent_loop.py`：原始异常脱敏和模型不能扩大 Tool/Policy 权限；
- `tests/evals/test_p1_agent_loop_tasks.py`：五个任务分别跑内存与 SQLite Store；
- `tests/integration/test_tool_executor.py`：记录式入口与旧入口共享执行行为。

F-0005 已用 production composition 和 CLI 调用这条 Loop；重启恢复、Approval 与 sandbox 仍未实现。
修改 Loop 时，先证明没有旁路已有 port，再更新 Feature Spec、架构、学习页、开发者页和当前状态。

F-0019 没有在 Loop 中增加 logger 分支。production bootstrap 只用 EventStore decorator 在 append 成功后
输出固定 Event 元数据；sink 失败不能改变这里描述的任何保存或调用顺序。继续阅读
[结构化诊断为什么不能成为第二套 Event](/zh-cn/development/diagnostics/)了解 Log、Event 和未来 Trace
之间的边界。
