---
title: F-0016 有界 Agent Loop 实现导读
description: 找到 ContextBuilder、v2 Event、串行协调器、费用估算和固定任务测试。
bearStatus: implemented
sourceRefs:
  - F-0016
  - PLAN-F-0016
  - ADR-0013
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
| `domain/run_events.py` | 同名 Event 的 v2 payload；v1 继续原样解析和重放 |
| `domain/tools.py` | 原始/规范化请求、Policy 决定、是否到达 adapter 和 ToolResult 的执行记录 |
| `runtime/context.py` | 只从已提交 v2 Event 构造 exact ModelRequest |
| `runtime/model_stream.py` | 有界组装 text delta、Tool call 和唯一 completion |
| `runtime/pricing.py` | input/output 分别向上取整的整数 micro-USD 估算 |
| `runtime/tool_executor.py` | `execute` 与 `execute_recorded` 汇合到同一个私有执行路径 |
| `application/agent_loop.py` | 保存边界、串行调度、终止和安全失败 |
| `evals/p1/` | 五个版本化任务定义与 workspace fixture |

## v2 Event 保存什么

新 Run 全部写 schema version 2，SQLite 表结构不变。RunCreated 保存目标、预算和非敏感 AgentConfig
快照；Model requested 保存 exact request 和 Context 报告；Model completed 保存 assistant Message、
Provider request ID、实际模型、finish reason、usage 和费用估算。

Tool requested 保存模型提出的原始 ToolRequest。Tool completed/failed 保存可用的
PreparedToolRequest、PolicyDecision、是否真正进入 adapter，以及完整 ToolResult。`workspace.write`
返回的 Artifact 因而随 ToolResult 进入 Event，RunResult 再从这条已校验结果提取元数据。

所有 Event 在进入 Store 前统一受 4 MiB、10,000 个 JSON node 和 32 层限制。exact ModelRequest
放不进 requested Event 时，Provider 不会被调用；模型完成内容放不进 completed Event 时，Run 记录
模型协议失败。若 Tool 已执行但完整执行记录过大，Loop 保存 `persistence_truncated=true` 的有限失败
记录，保留原始请求和 `reached_adapter`，随后终止 Run，不把可能已经发生的副作用自动重试。

Reducer 继续只读取 v1/v2 共有的状态字段，所以 projection schema 不需要 migration。解析 Event 时会
把冻结 JSON 容器还原成普通 JSON，再按事件类型和 schema version 严格校验。

## 三个容易改坏的边界

第一，Provider 和 Tool 只能在 started Event 提交成功后调用。任何 append 失败都原样向上返回；Loop
不会再追加一个“看起来更完整”的失败 Event，因为事实边界本身已经不可信。

第二，ToolExecutor 的两个公共入口只决定返回 `ToolResult` 还是完整执行记录。lookup、输入限制、
prepare、Policy、timeout、adapter 调用和输出检查只存在一份。Agent Loop 不能直接调用具体 Tool。

第三，调用者取消时 `CancelledError` 原样传播。模型或 Tool Activity 可能保持 RUNNING；F-0016 不
添加恢复、自动 retry 或 `UNKNOWN` 来掩盖这个事实。

第四，同一个 ToolCallRequested v2 与 terminal v2 必须包含值相等的原始 ToolRequest。这个检查读取
Event 历史，不给 Run/Activity projection 添加 v2 专属字段，所以 v1/v2 仍得到相同 projection。

## 从哪里看测试

- `tests/unit/test_context_builder.py`：固定层、Tool schema、完整交互组和截断；
- `tests/unit/test_agent_loop.py`：文本结束、多 Tool、Tool 失败、预算和协议失败；
- `tests/recovery/test_agent_loop_boundaries.py`：每个外部调用前后的 append 故障与取消；
- `tests/security/test_agent_loop.py`：原始异常脱敏和模型不能扩大 Tool/Policy 权限；
- `tests/evals/test_p1_agent_loop_tasks.py`：五个任务分别跑内存与 SQLite Store；
- `tests/integration/test_tool_executor.py`：记录式入口与旧入口共享执行行为。

当前没有 CLI 组装、重启恢复、Approval 或 sandbox。修改 Loop 时，先证明没有旁路已有 port，再更新
Feature Spec、架构、学习页、开发者页和当前状态。
