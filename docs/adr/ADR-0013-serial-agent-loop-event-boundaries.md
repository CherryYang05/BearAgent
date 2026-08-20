---
title: "ADR-0013: Drive the P1 Agent Loop serially across persisted Activity boundaries"
status: accepted
date: 2026-08-18
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0013：P1 Agent Loop 串行执行，并在外部调用前后保存 Activity 事实

## 要解决的问题

BearAgent 已经有 ModelProvider、ToolExecutor、EventStore、Reducer 和预算规则，但还没有模块负责把它们
接成一次 Run。最短的做法是让 Loop 在内存中维护 messages 和计数，只在结束时写结果；这样进程一旦
中断，数据库无法说明模型看到了什么、Tool 是否经过 Policy、文件写入是否已经发生，Context、CLI
和恢复也会各自形成一套事实。

现有 v1 Activity payload 只保存 ID、Tool 名称和模型 usage。F-0007/F-0008 已要求 F-0016 保存
规范化请求、ToolResult 和 Artifact；Roadmap 还要求保存完整模型响应、Provider request ID、Prompt/
Tool/Agent 版本。若直接给 v1 字段追加新含义，历史 Event 的 schema 会被静默改变。

现在必须统一三个边界：Loop 依靠什么决定下一步、外部调用和 Event append 的先后顺序，以及怎样在不
迁移 SQLite 表的情况下保存足够事实。

## 选择时最看重什么

- 可维护性：协调层只接线，继续复用现有 port、Reducer、预算、Policy 和 adapter；
- 恢复语义：每次外部调用前后都有已提交边界，不把内存状态或日志当事实；
- 安全：模型和 ToolResult 不能绕过 Policy；Runtime 不把自身凭据、配置根路径、临时名或原始异常
  主动复制进 Event，同时仍如实保存契约要求的用户/模型/Tool 不可信事实；
- 复杂度/交付时间：P1 保持单进程串行，不引入 graph/workflow framework、queue 或自动 retry；
- 兼容与迁移：保留 v1 Event 读取语义，优先复用现有 Event JSON 列和 projection 表。

## 比较过的方案

### 方案 A：Loop 维护内存消息和计数，结束时保存摘要

实现最短，模型和 Tool 可以很快串起来。但 Provider 已产生费用或文件已写入时，进程可能尚未保存
任何对应事实。ContextBuilder、inspect 和恢复只能相信不完整日志；预算也可能与 Reducer projection
分叉。该方案违背 ADR-0002/ADR-0009。

### 方案 B：串行 Loop 每次从已提交 Event 重建 Context，并使用 v2 Activity payload

每次 Activity 前用最新 projection 检查预算，先提交 requested/started，再调用 port，最后提交
completed/failed。ContextBuilder 只读取 v2 Event。v2 保存 exact ModelRequest、完整 assistant Message、
Tool 执行记录和版本快照；Reducer 同时读取 v1/v2 的共有状态字段。代价是 payload、Schema 和故障
注入测试明显增加。

### 方案 C：引入通用 graph 或 durable workflow engine

框架可以提供节点、重试和可视化，但 BearAgent 仍需把框架状态映射成自己的 Event、预算、Policy 和
未来 `UNKNOWN`。P1 只有一个串行 Loop，没有多 worker、timer 或补偿流程证据；现在引入会扩大依赖与
恢复语义，而不是消除它们。

## 决定

选择方案 B，并作出以下约束：

1. Agent Loop 位于 `application`，通过构造注入 `ModelProvider`、`EventStore`、`ToolExecutor`、clock
   和 ID generator。它不导入任何具体 Provider、SQLite、workspace 或 CLI adapter。
2. 一次 Run 串行执行。每次 Activity 前从 EventStore 返回的最新 RunState 调用既有预算检查；同时
   最多一个 PENDING/RUNNING Activity。
3. Loop 先提交 requested，再提交 started；只有 started 提交成功才调用外部 port。结果返回后提交
   completed/failed。任何 append 失败都停止后续调度。
4. `ContextBuilder` 是 Runtime 中的纯组件，只根据非敏感 AgentConfig、Registry ToolSpec 和该 Run
   已提交 v2 Event 构造 ModelRequest；它不读取日志、SDK 对象、数据库 row 或可变 adapter 状态。
5. Context 的固定顺序为 Runtime 规则、Agent 说明、用户目标、历史；ToolSpec 按名称排序。上限内先
   截短 ToolResult preview，再省略最早完整交互组，不拆开 Tool call/result，不自动总结。
6. AgentConfig 是冻结的版本快照。它包含模型/Prompt/定价/Context/Tool 名单，但不包含 key、base URL、
   workspace 绝对根或 client，也不授予权限。
7. 新 Run 使用同名 Event type 的 schema v2。v2 保存重建所需的 Provider-neutral 数据；v1 不改写，
   Reducer、内存 Store 和 SQLite Store 持续接受两版。现有 SQLite JSON Event 列与 projection 足够，
   F-0016 不增加 migration。
8. Model requested v2 保存 exact ModelRequest 和 Context 报告；completed v2 保存完整 assistant Message、
   Provider request ID、实际模型、finish reason、usage 与确定性费用估算。partial failure 不进入后续 Context。
9. Tool requested v2 保存模型提出的 ToolRequest；completed/failed v2 保存原始请求、可用的
   PreparedToolRequest、PolicyDecision 和完整 ToolResult。Artifact 只从该 ToolResult 取得。
10. ToolExecutor 增加记录式入口，但它与现有 `execute` 必须委托给同一私有执行流程。lookup、prepare、
    Policy、timeout 和 adapter 调用只能存在一份，Agent Loop 不能直接调用 Tool。
11. Tool 的结构化失败作为 is_error Tool message 返回模型，由模型在剩余预算内纠正；Loop 不自动 retry。
    Model/协议失败、预算耗尽、Context 不可构建或事实边界失败直接终止或停止 Run。
12. `CancelledError` 原样传播。EventStore 在外部调用后失败或进程中断时，Run 可以保持非终态；Loop
    不伪造成功、不重试写入，也不提前增加 P2 的 `UNKNOWN`。
13. Provider usage 使用 AgentConfig 中带版本的整数费率计算预算估算：input/output 分别按每百万 token
    向上取整到 micro-USD。它不是账单；更复杂计费需要新版本契约。
14. 默认证据使用五个版本化 Fake Provider 任务。真实模型与 CLI 组装属于 F-0005/P1 收尾，不进入
    默认 CI，也不读取开发者凭据。
15. Event payload 的 4 MiB byte、10,000 node 与 32 层限制属于领域契约，内存和 SQLite Store 必须
    一致执行。requested/completed 无法持久化时在调用前拒绝或改记安全失败；Tool 已执行但完整记录
    超限时，保存含原始请求、`reached_adapter` 和 `persistence_truncated` 的有限失败事实并终止 Run。

## 带来的影响

### 得到的好处

- Context、Loop、Store 和以后 CLI 使用同一批 Event，不维护第二份消息或预算真相；
- 每次外部调用是否越过持久边界可由 sequence 检查，故障注入有明确断言点；
- v1 历史 Run 继续可读，新 Run 保存足够 Provider-neutral 事实供 inspect、eval 和 P2 使用；
- Tool 仍只有一条 Registry -> prepare -> Policy -> bounded execution 路径；
- Fake Provider 可以确定性证明多轮模型/Tool 接线，无需网络或真实 key；
- 不增加生产依赖、数据库 migration、后台 worker 或工作流框架。

### 接受的代价

- v2 Event 可能包含较大的 ModelRequest、assistant Message 和 ToolResult，必须维持统一的 byte/node
  上限；超限后的有限 Tool 记录会牺牲完整结果，但明确保留是否越过 adapter 边界；
- 每个 Activity 至少产生 requested/started/terminal 三次 transaction，P1 接受本地 SQLite 写放大；
- 每次模型调用从 Event 重建 Context，比维护可变内存列表多一些解析工作；
- Provider 调用或 Tool 写入可能发生，而 terminal Event append 失败；P1 只停下，不恢复或 reconcile；
- 取消后 Activity 可能保持非终态，直到 P2 定义恢复/取消事实；
- 定价是版本化估算，不能覆盖缓存 token、折扣或 Provider 最终账单差异；
- F-0016 完成后仍没有用户 CLI，必须由 F-0005 组装 production adapters。

## 迁移和回退

现有 Event payload JSON 与 SQLite projection 不变，因此没有 SQL migration。实现新增 v2 payload registry
和 Reducer 兼容分支；契约测试必须证明历史 v1 fixture 继续得到相同 RunState。

一旦任何 v2 Event 已提交，回退不能删除 v2 解析代码或把数据库降级为只认识 v1。可以停止创建新 Run
或移除未发布的 application 入口，但必须保留读取/重放兼容。`outputs/**` 属于用户结果，回退不删除。
若以后要改变 Context 或 Event 事实边界，使用新的 Event 版本和 superseding ADR，不原地改 v2。

## 怎样验证

- 同一 AgentConfig、ToolSpec 和 Event 序列重复构建 exact ModelRequest，结果值相等；
- v1/v2 Event 在内存与 SQLite Store 上运行同一 contract suite，projection 一致且无需 migration；
- 在 requested、started、外部返回、terminal append 和 Run terminal 各边界注入失败，断言调用次数与状态；
- Fake Provider 多轮提出读/搜/写 Tool，断言 Executor 单路径、Policy 结果、Event sequence 和 Artifact hash；
- 测试预算五维、多个串行 Tool call、Tool failure 回馈、Provider failure、空终止、timeout 和取消；
- 搜索 Runtime 生成的 Event 元数据、日志、Context 报告和 Error，确认系统没有主动泄露 key、
  authorization、workspace 绝对根、临时名或原始异常；不对按契约保存的不可信内容做字面过滤；
- 运行 Schema、Ruff、Pyright、pytest、文档链接、Starlight、package build 和 import boundary 检查；
- P2 开始时重新评估 non-terminal Activity、外部写后 append 失败、Attempt、Receipt 和 `UNKNOWN`。

项目所有者于 2026-08-18 接受本决定。
