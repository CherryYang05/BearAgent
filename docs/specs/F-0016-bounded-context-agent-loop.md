---
title: "Feature: Bounded context and serial Agent Loop"
status: implemented
spec_id: F-0016
milestone: P1
owner: CherryYang05
created: 2026-08-18
last_updated: 2026-08-27
implemented_in: "PR #12"
related_adrs:
  - ADR-0001
  - ADR-0002
  - ADR-0004
  - ADR-0005
  - ADR-0007
  - ADR-0009
  - ADR-0010
  - ADR-0011
  - ADR-0012
  - ADR-0013
---

# F-0016：把模型、Tool 和 Event 接成一条有界的文件任务执行链

## 1. 为什么现在要做

用户希望 BearAgent “阅读 `docs/`，把一份项目介绍写到 `outputs/intro.md`”。仓库目前已经能分别：

- 用 `ModelProvider` 调用模型；
- 用 `ToolExecutor` 安全执行四个 workspace Tool；
- 用 `EventStore` 原子保存 Event 和 projection；
- 用 Reducer 与预算检查计算 Run 状态。

但这些边界还没有接在一起。现在没有代码负责把用户目标组织成模型请求、把模型提出的 Tool call 交给
Executor、把结果交回模型，或者把每一步保存为 Event。即使单独调用各个 adapter，也不能称为一次
可检查的 Run。

F-0016 只补上这条执行链。它提供可由 application 层调用的串行 Agent Loop 和确定性任务集；命令行
入口与 `inspect/events` 留给 F-0005。

## 2. 本次交付

- 冻结且有界的 `AgentConfig`，保存 Agent、Prompt、模型、定价和 Context 规则的版本化快照；
- `ContextBuilder`，从已提交 Event 按稳定顺序生成 Provider-neutral `ModelRequest`；
- 单进程、单 Run、串行 Activity 的 Agent Loop application service；
- 每次模型和 Tool Activity 前后的 v2 Event payload，保存可重建执行过程的有界事实；
- `ToolExecutor` 的有界执行记录，让 Loop 能保存规范化请求、Policy 决定和 `ToolResult`，但仍只有
  一个实际执行入口；
- 五个版本化固定任务与 Fake Provider 脚本，覆盖读取、搜索、写入、受控替换和预算/路径拒绝；
- 单元、契约、集成、安全和确定性 eval 测试；
- 工程文档、初学者路径、开发者入口和当前状态同步。

## 3. 本次不做

- 不增加 `bearagent run`、`run inspect` 或 `run events` CLI；这些属于 F-0005；
- 不增加 Checkpoint、启动恢复、pause/resume/cancel、自动 retry、Attempt、Receipt 或 `UNKNOWN`；
- 不增加 Approval、Grant、可配置 Policy、sandbox、shell、代码执行或网络 Tool；
- 不增加 MCP、Skill、Memory、RAG、自动摘要或模型生成的上下文压缩；
- 不并行执行 Tool，不运行多个 Agent，不增加 workflow/graph 框架；
- 不让 Agent 配置、Prompt、workspace 内容或 ToolResult 创建权限；
- 不修改 `outputs/**` 以外的文件，也不自动删除成功 Artifact；
- 不把真实模型 4/5 的 P1 退出演练作为默认 CI；F-0005 接好生产组装和 CLI 后再执行该演练。

## 4. 需要先说明的约定

### AgentConfig 不是权限

`AgentConfig` 说明“这个 Agent 使用哪个模型、哪些说明和哪些 Tool schema”。它可以缩小暴露给模型的
Tool 集合，但不能扩大 Policy 权限。即使配置写着 `workspace.write`，固定 Policy 没有允许时，执行仍
必须返回拒绝。

配置快照至少包含 Agent ID/版本、模型名、Prompt 版本、可信说明、最大模型输出、模型 timeout、
Context 上限、ToolResult 预览上限、Tool 名单和版本化定价。API key、base URL、workspace 绝对路径
和 Provider client 不属于配置。

### ContextBuilder 只整理已经保存的事实

`ContextBuilder` 不自己调用模型或 Tool，也不维护第二份聊天历史。它读取已提交的 v2 Event，按固定
顺序放入 Runtime 规则、Agent 说明、用户目标、Tool schema 和完整的最近交互。超过 Context 上限时，
它先缩短过大的 ToolResult 预览，再丢弃最早的完整交互组；不会把一条 Tool call 和对应结果拆开，
也不会让模型自动总结被省略的内容。

每次模型 Activity 的 requested Event 保存实际 `ModelRequest` 和 Context 省略报告。因此以后可以检查
模型看到了什么，而不是根据日志猜测。

### Agent Loop 只决定下一步怎样接线

Loop 是 application 层协调器。它不重新实现 Reducer、预算、Policy、Provider 或文件规则：

```text
已提交 Event -> ContextBuilder -> ModelProvider
       ^                              |
       |                              v
EventStore <- ToolExecutor <- ToolRequest
```

Loop 每次只允许一个 active Activity。它在外部调用前先提交 requested/started Event，调用结束后再提交
completed/failed Event。进程中断时只相信已经提交的事实。

### 费用是版本化配置计算出的估算值

Provider 当前只返回 token usage，不返回可直接核对的账单金额。F-0016 用 AgentConfig 中带版本的
每百万 token 整数费率计算 `cost_microusd`，输入和输出分别向上取整到 micro-USD。这个值用于稳定预算
和本地比较，不宣称等于 Provider 最终账单；缓存 token、批量折扣等计费能力以后需要新契约。

## 5. 使用场景

### 读取并生成项目介绍

application 创建一个包含目标、预算和 AgentConfig 的 Run。Loop 提交 `RunCreated/RunStarted`，构造
第一次模型请求。Fake Provider 或真实 Provider 提出 `workspace.list/read/search`；每个请求串行经过
Registry、prepare、Policy 和 Executor，结果保存后再进入下一次 Context。模型最后调用
`workspace.write`，Artifact 元数据进入 Tool completed Event；模型返回最终说明后 Run 成功。

### 模型请求越界路径后自行纠正

模型先请求读取 `../secret.txt`。Executor 返回稳定的路径错误，没有文件内容泄露。Loop 把错误作为
ToolResult 交回模型，并继续遵守剩余预算。模型随后可以改用 `docs/architecture/overview.md`。Policy
拒绝或 Tool 失败本身不自动让 Run 终止；模型失败、协议损坏或预算耗尽才终止 Run。

### 预算不足时停止

低预算 Run 完成一次模型 Activity 后已经达到模型次数、token、费用或总时间上限。Loop 在创建下一条
Activity requested Event 前得到 `BudgetExhaustion`，提交 `RunFailed`，不再调用 Provider 或 Tool。

### 写入成功后 EventStore 暂时失败

`workspace.write` 可能已经原子提交文件，但 completed Event 还未保存。Loop 立即停止，不自动重试，
也不把 Run 写成成功。文件可能存在而 Run 保持非终态；P2 才通过路径和 hash reconcile，F-0016 不猜测。

## 6. 必须满足的行为

### 6.1 Run 创建和配置

- application 输入只接受已校验的 SessionId、非空有界目标、BudgetLimits 和 AgentConfig；
- `RunCreated` v2 保存目标、完整非敏感 AgentConfig 快照和预算；Event 是后续 Context 的事实来源；
- AgentConfig 的 Tool 名单必须无重复、稳定排序并且全部存在于 Registry；它不替代 Policy allowlist；
- Agent、Prompt、定价和 Context 规则都带稳定版本；运行中不能被可变调用方集合或对象静默改变；
- clock、ID generator 和外部 port 通过构造边界注入，确定性测试不依赖真实时间或随机顺序。

### 6.2 ContextBuilder

- 第一层是版本化 Runtime 安全规则，第二层是 Agent 说明，第三层是用户目标；随后才是历史；
- Tool schema 从 Registry 的注册时 `ToolSpec` 转成 `ModelToolDefinition`，按名称稳定排序；
- Context 只从该 Run 已提交的 v2 Event 重建，不读取日志、SQLite row、Provider SDK 对象或 adapter 状态；
- ToolResult 使用确定性 JSON 文本进入 Tool message；失败结果显式设置 `is_error=true`；
- 超大 ToolResult 先变成带 `truncated`、原始 byte 数和有限 preview 的稳定 JSON envelope；完整结果仍在 Event；
- 总 Context 超限时按最早到最新丢弃完整交互组，保留 Runtime 规则、Agent 说明、目标和最近完整交互；
- Tool call 与其全部 ToolResult 是一个不可拆分组。无法在上限内放入固定层或一个必要组时，构建明确失败；
- 每次构建返回确切 `ModelRequest` 和省略/截断报告；同一 Event、配置和 ToolSpec 得到值相等结果；
- 不执行 tokenization、自动摘要、向量检索或隐藏的 Provider 会话续接。

### 6.3 模型 Activity

- 每次模型调用前先从最新 RunState 执行 `check_activity_budget`；拒绝时不创建 Model Activity；
- budget 允许后依次提交 ModelCallRequested v2 和 ModelCallStarted v2，再调用 `ModelProvider.stream`；
- requested payload 保存 exact ModelRequest 和 Context 报告；Started 提交失败时 Provider 零调用；
- Loop 只接受有限 text delta、完整 Tool call 和唯一 completed Event，并组装一个冻结 assistant Message；
- completed v2 保存 assistant Message、Provider request ID、实际模型名、finish reason、已知 usage 和估算费用；
- Provider 失败或流协议失败保存 ModelCallFailed v2 与 `RunFailed`，不自动重试；已出现的 partial output
  不进入下一次 Context，也不作为最终回答；
- `finish_reason=tool_calls` 必须至少包含一个 ToolCallPart；`finish_reason=stop` 必须有非空文本且不能有
  未处理 Tool call，否则以协议错误失败；
- 模型返回多个 Tool call 时按返回顺序串行处理，任何时刻仍只有一个 active Activity。

### 6.4 Tool Activity

- ModelToolCall 只转换成 BearAgent `ToolRequest`，不能直接导入或调用 workspace adapter；
- 每个 Tool call 前重新检查工具次数、token、费用和总时间预算；拒绝时不调用 Executor；
- Loop 提交 ToolCallRequested v2 和 ToolCallStarted v2 后，只能调用 ToolExecutor 的记录式执行入口；
- 记录式入口与现有 `execute` 共用 lookup、prepare、Policy、timeout、执行和结果检查代码，不产生第二条旁路；
- completed/failed v2 在统一 Event 上限内保存原始 ToolRequest、可用时的 PreparedToolRequest、
  PolicyDecision 和完整 ToolResult；
- 如果完整执行记录超过 Event 上限，Loop 保存带 `persistence_truncated=true` 的有限失败记录：保留原始
  ToolRequest、是否到达 adapter 和安全错误，丢弃超大的规范化输入/结果，然后终止 Run，不自动重试；
- Policy/prepare/lookup 失败也形成有限 ToolResult；未进入 adapter 时不能谎称 Tool 已执行；
- ToolResult 成功或失败都作为一条 tool Message 进入后续 Context。Tool 失败不自动重试，也不自动终止 Run；
- Artifact 只从已校验 ToolResult 读取并保存在 Event 中；Loop 不自己打开或修改 Artifact 路径。

### 6.5 终止、失败和取消

- 模型以合法 stop 完成且没有待处理 Tool call 时，Loop 提交 `RunSucceeded` 并返回冻结 Run 结果；
- 预算耗尽、ModelProvider/协议失败、Context 构建失败或不可继续的内部边界错误提交安全 `RunFailed`；
- exact ModelRequest 无法装入 requested Event 时不调用 Provider；模型完成内容无法装入 completed Event
  时改记 ModelCallFailed。两种情况都安全终止 Run；
- Tool 的结构化失败交回模型；如果下一步因预算耗尽无法请求模型，Run 以预算错误失败；
- `asyncio.CancelledError` 原样传播，不被改写成普通 failed。已经提交的 Run/Activity 保持非终态；
- 任一 Event append 失败后停止调度，不调用后续外部能力。已经发生的 Provider 费用或文件写入不重试；
- timeout 不撤销已经发生的外部行为。F-0016 不产生 `UNKNOWN`，也不把非终态投影显示为成功；
- Loop 没有自动 retry。未来 retry 必须先增加 Attempt、幂等与恢复语义。

### 6.6 固定任务集

- 任务定义包含 task ID/版本、目标、workspace fixture、AgentConfig 版本、预算、预期 Tool 路径和终止原因；
- 五项任务分别覆盖：单文档介绍、多文档汇总、带来源比较、已有输出替换，以及路径拒绝后因低预算终止；
- Fake Provider 使用逐次请求脚本，而不是根据 Prompt 做隐藏分支；请求数量、Tool 顺序和参数可断言；
- 默认 CI 运行 5/5 Fake 任务，不访问网络、不读取凭据、不依赖模型随机性；
- 真实模型演练复用同一任务定义，但凭据、模型可用性和 4/5 结果留给 F-0005/P1 收尾报告。

## 7. 对外入口和模块连接

| 模块 | F-0016 的变化 |
|---|---|
| `domain` | AgentConfig、Context 报告、Run 输入/结果、Tool 执行记录和 v2 Event payload |
| `runtime` | 纯 ContextBuilder、费用计算和 ToolExecutor 的单路径记录能力 |
| `application` | 串行 Agent Loop，用注入的 ports、clock 和 ID generator 协调一次 Run |
| `ports` | 继续使用 ModelProvider、EventStore、Tool 和 Policy；不引入 adapter 类型 |
| `adapters/testing` | 可脚本化 Fake Provider 与固定任务测试辅助 |
| `adapters/sqlite` | 不改表结构；同一 JSON Event 列保存 v1/v2 payload |
| `bootstrap/interfaces` | F-0016 不组装生产 CLI；F-0005 后续复用 application service |

依赖方向保持 `interfaces -> application -> runtime/domain/ports`，adapter 实现 port。Runtime 不导入
SQLite、OpenAI SDK、workspace adapter 或 CLI。application 只协调，不复制 Reducer、Policy 或路径规则。

## 8. 状态和保存的数据

现有 v1 Event 继续原样解析和重放。F-0016 为同名 Run/Activity Event 增加 v2 payload；不修改历史
payload 的含义，也不重写已提交 Event。Reducer 同时接受白名单 v1/v2，并从两版共有的状态字段计算
相同 projection。

新 Run 全部写 v2。v2 至少增加：

- `RunCreated`：目标和非敏感 AgentConfig 快照；
- `ModelCallRequested`：exact ModelRequest 和 Context 报告；
- `ModelCallCompleted`：完整 assistant Message、Provider 元数据、usage 和估算费用；
- `ModelCallFailed`：安全 Error、已知 usage/费用和是否丢弃 partial output；
- `ToolCallRequested`：模型提出的 ToolRequest；
- `ToolCallCompleted/Failed`：PreparedToolRequest/PolicyDecision（可用时）和完整 ToolResult。

Event 仍写入现有 `events.payload_json`；Run/Activity projection 字段不变，因此没有 SQLite migration。
Event 领域契约统一限制 payload 为 4 MiB、10,000 个 JSON node 和 32 层；内存与 SQLite Store 因此在
adapter 之前接受或拒绝同一 Event。Context 和 F-0005 查询只使用 BearAgent payload，不解析 Provider
SDK 对象或文件 adapter 内部状态。

## 9. 失败时会发生什么

- 配置/目标无效：Run 创建边界拒绝；没有外部调用；
- Context 固定层超限或历史无法形成合法消息：Run 安全失败，不创建 Model Activity，也不调用 Provider；
- exact ModelRequest/Event payload 聚合超限：Run 安全失败；内存与 SQLite Store 结果一致；
- Provider timeout、认证、限流、协议损坏：记录现有安全 Error 分类，Run 失败，不重试；
- Tool not found、prepare、Policy、timeout 或 adapter 失败：记录完整安全 ToolResult，交回模型；
- Tool 已返回但完整执行记录无法装入 Event：保存有限 ToolCallFailed 与 RunFailed；`reached_adapter`
  仍说明外部行为可能已经发生，Loop 不重试；
- EventStore 在外部调用前失败：外部调用不发生；
- EventStore 在 Provider 返回后失败：费用可能已发生，Loop 停止，Run 不冒充成功；
- EventStore 在 workspace.write 返回后失败：完整文件可能存在，Loop 停止且不重试，P2 再 reconcile；
- 调用者取消：取消原样传播，最后已提交 Activity 可能保持 PENDING/RUNNING；
- 进程中断：已提交 Event 可查询，非终态 Run 不自动继续，也不显示成功。

## 10. 安全与隐私

- 模型、目标、workspace 内容和 ToolResult 都是不可信数据，不能修改 AgentConfig、BudgetLimits、
  ToolSpec、Policy 或 Context 上限；
- 所有外部文件动作仍通过 ToolExecutor 与固定 Policy，Loop 没有 adapter 直连入口；
- Runtime 不得把自身持有的 API key、authorization header、Provider client/base URL、workspace
  绝对根、原始异常、临时文件名或完整敏感日志主动复制进 Event、Context 报告和错误；用户目标、
  模型参数或 ToolResult 属于必须按契约保存的不可信事实，其中可能自然出现相同字面文本；
- ModelRequest 和 Event 都有字符、byte、节点、深度、消息、Tool 数量和 timeout 上限；
- Context 截断不能去掉 Runtime/Agent 安全规则，也不能把 ToolResult 文本当成 system instruction；
- AgentConfig 的 Tool 名单只决定暴露 schema，不授权执行；Prompt injection 要求提权仍由 Policy 拒绝；
- F-0016 仍是单用户、单进程受控本地运行，不把应用层边界描述成 P3 sandbox。

## 11. 怎样检查执行过程

开发者可以用 `EventStore.list_events` 查看完整有序事实：创建配置、每次 exact ModelRequest、模型完成
元数据、Tool 原始/规范化请求、Policy 决定、ToolResult、Artifact、预算用量和终止 Error。

F-0016 的 Python 返回值提供 RunId、终态、最终文本和本次 Artifact 元数据。F-0005 后续把相同
application 结果与 Event 转成人类输出和 `--json`，不重新解析日志或维护第二套状态。

默认结构化日志只记录 RunId、ActivityId、Event type、sequence、耗时和有限错误码，不复制目标全文、
模型全文、Tool 参数、ToolResult 或凭据。token delta 可由调用者观察，但不逐 token 写 WAL。

## 12. 上线与回退

F-0016 先通过 application Python 接口和 Fake Provider 测试启用；没有默认 CLI、网络调用或数据库
migration。F-0005 以后才在 bootstrap 组装真实 Provider、SQLite、workspace Tool 和 CLI 参数。

回退时必须保留 v2 Event 的解析/重放兼容代码，不能让已经提交的 Run 变成“未知版本”。可以移除
未发布的 Loop 入口和任务集，但不能改写历史 Event，也不能删除用户 `outputs/**`。如果决定完全撤销
v2，需要新的兼容性 ADR 和明确数据迁移，而不是降级数据库文件。

## 13. 验收标准

- AC-1：当 Fake Provider 按脚本请求读取、搜索和写入时，Loop 应只通过 ModelProvider、ToolExecutor
  和 EventStore 串行完成任务，生成 hash 可核对的 Artifact，并以 `RunSucceeded` 结束；
- AC-2：当同一配置、ToolSpec 和 Event 序列重复构建 Context 时，系统应生成值相等的 ModelRequest；
  超限时应按固定规则截断/省略，且 Runtime 规则、目标和完整最近交互不被拆散；
- AC-3：当任一预算维度阻止下一次 Activity 时，系统应在外部调用前提交安全 `RunFailed`，Provider
  或 Tool 的调用次数不再增加；
- AC-4：当模型请求越权、无效或不存在的 Tool 时，系统应记录原始请求、可用的规范化/Policy 信息和
  安全 ToolResult，不发生旁路副作用，并允许模型在剩余预算内纠正；
- AC-5：当 Provider 失败、流协议损坏或返回空终止结果时，系统应记录 ModelCallFailed 与 RunFailed，
  丢弃 partial output 且不自动重试；
- AC-6：当调用被取消或 EventStore 在外部调用后失败时，系统应停止调度、不自动重试、不伪造终态；
  已提交事实与可能存在的外部结果保持可检查；
- AC-7：当重放已有 v1 Event 或新 v2 Event 时，内存和 SQLite store 应得到一致 projection；v1 schema
  含义不变，SQLite v1 表结构无需 migration；
- AC-8：当检查 Runtime 生成的 Event 元数据、Context 报告、Error 和日志时，不应发现由系统主动泄露的
  API key、authorization、workspace 绝对根、原始异常或临时文件名；按契约保存的用户/模型/Tool
  不可信内容不作字面过滤；AgentConfig/Prompt 不能扩大 Policy 权限；
- AC-9：当给定固定 token usage 和版本化整数费率时，系统应确定性计算费用并由 Event/Reducer 记账；
  文档应明确它是预算估算值而非 Provider 账单；
- AC-10：当默认 CI 运行五个版本化固定任务时，Fake Provider 应达到 5/5，并断言预期 Tool 顺序、
  参数、Event 序列、Artifact 或结构化失败；测试不得访问网络或读取真实凭据；
- AC-11：当运行完整验证时，单元、契约、集成、安全、Schema、Ruff、Pyright、文档链接、站点、构建
  和 import boundary 检查应全部通过，且站点明确 CLI、恢复、Approval 和 sandbox 仍未实现。

## 14. 验证方式

- Unit：AgentConfig/定价、Context 稳定顺序与截断、消息组完整性、模型流组装、终止判断和 Event 工厂；
- Contract：v1/v2 payload Schema、EventStore 双实现重放、Fake Provider 多轮脚本和 Tool 执行记录；
- Integration：Fake Provider + InMemory/SQLite EventStore + 四个真实 workspace Tool 完成固定任务；
- Recovery：在每个 Event append 边界注入失败，证明后续调用停止；外部写后失败保持非终态且不重试；
- Security：Prompt/ToolResult 提权、Policy 旁路、Context 注入、secret/路径/异常脱敏、超大输入和取消；
- Eval/manual：默认 5/5 Fake；可选真实模型 dry run 只在用户显式提供凭据时执行，不作为默认 CI。

## 15. 文档同步

- [x] Engineering source of truth：Spec、Plan、ADR、Architecture、Roadmap、Schema；
- [x] Site beginner learning path：从“一次文件任务怎样走完”解释 Context、模型、Tool 和 Event；
- [x] Site developer documentation：Loop 边界、v2 Event、截断、预算和故障窗口；
- [x] Site current status：说明 application Loop 已实现但 F-0005 CLI、P2 恢复和 P3 Approval/sandbox 未实现；
- [x] Architecture / ADR：更新当前代码、Context/Loop 和 Event 保存路径；
- [x] Deployment docs：确认仍无公开服务、生产 CLI 组装或新 secret 存储；
- [x] Generated reference：AgentConfig、Context 报告、执行记录和 v2 Event Schema。

## 16. 已确认的决定

1. Context 默认总上限 524,288 characters，单个 ToolResult preview 上限 65,536 UTF-8 bytes；先缩短 ToolResult，
   再按最早完整交互组省略，不自动写隐藏 Artifact；
2. AgentConfig 保存版本化的每百万 input/output token 整数 micro-USD 费率；两部分分别向上取整，作为
   本地预算估算，不宣称等于账单；
3. Tool 的结构化失败默认交回模型继续推理，只有模型失败、Context 无法构建、预算耗尽或内部事实
   边界失败才直接终止 Run；
4. v2 使用同名 Event type 加新 payload 版本；新 Run 全写 v2，Reducer/Store 永久保留 v1 读取兼容，
   现有 SQLite 表不迁移；
5. F-0016 交付五个 5/5 Fake 任务和可选真实模型入口；真实模型 4/5 与 CLI 演示在 F-0005/P1 收尾完成。

项目所有者于 2026-08-18 接受本 Spec 和以上五项决定。
