---
title: "Feature: ModelProvider internal interface and first production adapter"
status: implemented
spec_id: F-0004
milestone: P1
owner: CherryYang05
created: 2026-08-13
last_updated: 2026-08-13
implemented_in: null
related_adrs:
  - ADR-0007
  - ADR-0010
---

# Feature: ModelProvider 内部接口与首个生产适配器

## 1. Background / Problem

BearAgent 已有不依赖特定模型服务商的 Message、Run/Activity、预算与持久 Event，但 P0 的
`ModelRequest`/`ModelEvent` 仍是只支持文本的最小 dataclass，`FakeModelProvider` 也没有稳定的
错误、用量、工具调用、超时或响应身份规则。运行时因此还不能在不接触外部 SDK 类型的
前提下调用真实模型。

## 2. Goals

- G-1：定义与模型服务商无关、可序列化且有大小限制的模型请求、流式事件、用量与响应信息格式。
- G-2：提供首个基于 OpenAI Responses API 的生产适配器，并把 SDK 对象完全限制在适配器内部。
- G-3：把文本增量、完整函数调用、结束原因、实际用量、模型标识和服务商请求 ID 转成 BearAgent 的内部格式。
- G-4：把请求失败、流中断、模型服务商拒绝和协议损坏转换为安全、可判定是否可重试的错误。
- G-5：用共用接口测试证明 Fake 与生产适配器遵守同一组内部接口规则。

## 3. Non-goals

- NG-1：不实现 ContextBuilder、Agent Loop、Activity 调度或 Event append；这些属于 F-0016。
- NG-2：不实现 ToolRegistry、ToolExecutor、Policy 或 workspace Tool；这些属于 F-0006 至 F-0008。
- NG-3：不在 F-0004 内自动重试；适配器只分类错误，后续运行时决定是否以及何时重试。
- NG-4：不实现多模型服务商聚合、备用服务切换、负载均衡、后台任务、WebSocket 或多模态输入。
- NG-5：不保存 API key、authorization header、原始 SDK 异常、完整请求或完整响应日志。

## 4. Terms and assumptions

- **内部接口（Port）**：核心代码可见的调用规则；这里只接收和返回 BearAgent 自己的数据类型，
  不暴露外部 SDK 对象。
- **适配器（Adapter）**：位于外层的协议翻译实现；它把 OpenAI 请求、流式事件和异常转换为
  上述内部接口的数据与错误。
- **JSON Schema**：描述工具参数允许哪些 JSON 字段和形状的数据规则，不代表工具执行权限。
- **模型服务商请求 ID**：外部模型服务返回的响应 ID，只用于关联与检查，不替代 BearAgent
  `ModelCallId`。
- **模型完成事件**：一次成功的流式响应中唯一的 `completed` 事件；失败以
  `ModelProviderError` 结束流，不伪造完成结果。
- F-0004 使用 Responses API 的 HTTP/SSE 流式响应；模型名由程序组装与配置入口传入，不在
  内部数据模型中写死“最新模型”。
- 项目所有者于 2026-08-13 明确启动 F-0004。

## 5. User scenarios

### Scenario A: text response

Given 一个合法的内部模型请求，When 适配器收到文本增量和成功完成事件，Then 调用者按序
获得文本增量和唯一完成事件，并能检查模型、用量、结束原因与模型服务商请求 ID。

### Scenario B: function call

Given 请求声明了一个带 JSON Schema 的 Tool，When 模型服务商返回完整函数调用，Then 适配器产生
一个带 BearAgent `ToolCallId`、名称和已验证 JSON object 参数的工具调用事件，且 SDK 类型不会越过
内部接口进入运行时。

### Scenario C: transient failure

Given 模型服务商限流、超时、连接失败或返回 5xx，When 请求或流式响应失败，Then 适配器抛出安全且
`retryable=true` 的模型服务错误；错误不包含密钥或原始响应正文。

### Scenario D: permanent or malformed failure

Given 认证/权限/参数错误，或模型服务商返回无效函数参数、缺失完成事件、重复完成事件，
When 适配器处理响应，Then 它按失败处理，返回 `retryable=false` 的安全错误且不产生完成结果。

## 6. Functional requirements

- FR-1：`ModelRequest` 至少包含模型名、消息、可选工具、最大输出 token、超时和提示词版本；
  集合与文本/JSON Schema 大小必须有限制。
- FR-2：Tool 定义只包含与模型服务商无关的名称、说明和 JSON object 输入规则；未知字段
  与非 JSON 值必须被拒绝。
- FR-3：模型流只暴露 BearAgent 定义的文本增量、工具调用与完成事件。
- FR-4：完成事件至少包含模型服务商请求 ID、实际模型、结束原因、输入/输出 token；
  未提供的用量不能猜测。
- FR-5：一个成功的流式响应必须恰有一个完成事件；完成后的额外事件、重复完成或没有完成事件
  都按协议错误处理。
- FR-6：函数参数必须是 JSON 对象；无效 JSON、数组/单值、重复工具调用 ID 或名称冲突均安全失败。
- FR-7：适配器必须设置有限超时并支持调用者取消；Python 取消信号要原样传播，不能转成可重试错误。
- FR-8：适配器不自动重试；错误分类至少区分临时故障、超时、限流、认证/权限、非法请求、
  内容拒绝与响应格式损坏。
- FR-9：模型 SDK 类型只能出现在 `adapters/model/` 内，内部数据、运行时和内部接口模块不得导入 SDK。
- FR-10：模型服务的替代实现可按预设脚本返回成功或失败的流，并保留内部请求供确定性断言。

## 7. Interfaces

`ModelProvider.stream(request) -> AsyncIterator[ModelEvent]` 这个内部接口保持不变，但请求和事件升级为
Pydantic 校验的数据模型。F-0004 不增加 CLI/API；生产适配器由后续程序装配入口使用。

## 8. State and data model

- `ModelRequest`、Tool 定义、用量、完成信息和按 `kind` 区分的 `ModelEvent` 加入公共
  JSON Schema 快照。
- F-0004 不新增 Event 类型、SQLite 列或数据迁移。F-0016 将把模型完成信息和用量转换为现有
  `ModelCallCompleted`/`ModelCallFailed` 事件数据并追加到 EventStore。
- 模型服务商响应 ID 与 BearAgent `ModelCallId` 分离；工具调用 ID 由适配器映射为
  `ToolCallId`，不能依赖服务商 ID 满足 UUID4 格式规则。

## 9. Failure and recovery semantics

- 请求建立前或流式返回中失败都会终止迭代器；已经发出的文本增量/工具调用只是临时观察，
  不代表 Activity 成功。
- 超时、连接错误、429 与 5xx 标记为可重试；认证、权限、非法参数、内容拒绝与协议损坏默认
  不可重试。
- 适配器不在内部重试，避免隐藏额外费用、重复流式响应或破坏 F-0016 的尝试/Event 记录。
- `asyncio.CancelledError` 原样传播；F-0004 不写取消事件，也不承诺 P2 的崩溃恢复能力。
- F-0004 没有外部副作用，不引入 `UNKNOWN`；模型调用可能产生费用，但不会自动重发。

## 10. Security and privacy

- API key 只通过 SDK 和程序组装边界注入，不进入 `ModelRequest`、Event、日志或错误详情。
- 错误详情只允许安全的状态、请求 ID 和服务商错误码；不复制响应正文、响应头、提示词或输出。
- 模型名、提示词版本、工具名/说明/输入格式与消息数量均验证长度；超时和输出 token 有上限。
- 模型服务商输出不可信。函数名、参数与模型完成字段在进入内部数据模型前验证；它们不能授予
  Tool 权限或直接触发副作用。
- Tool 输入格式只是请求描述，不是 Grant（运行时权限）；F-0006/P3 仍必须在执行前经过执行器和策略检查。

## 11. Observability

- 成功的模型完成事件暴露服务商请求 ID、实际模型、结束原因和用量，供 F-0016 持久化。
- 安全错误可暴露服务商状态、错误码和请求 ID，但不暴露敏感信息或原始响应正文。
- 本 Feature 不引入日志或指标后端，也不逐 token 持久化。

## 12. Rollout and rollback

- 新 SDK 依赖与适配器可在未被程序装配入口注册时安全落地；默认 CLI 行为不变。
- 回退时删除生产适配器和新的模型数据格式，恢复 P0 Fake；没有数据库迁移或外部状态需要回滚。
- 一旦公共数据格式由后续 Feature 持久化，不兼容变更必须增加版本和旧事件升级转换，而不是原地改变含义。

## 13. Acceptance criteria

- AC-1：公共数据格式拒绝空/超长模型名、空消息、非法超时/token、非 JSON/非对象的 Tool 输入格式。
- AC-2：Fake 与 OpenAI 适配器对合法文本流都按序产出文本增量和唯一完成事件。
- AC-3：OpenAI 适配器把完整函数调用映射为 BearAgent 工具调用，并拒绝非法 JSON/object/name。
- AC-4：模型完成事件保留请求 ID、实际模型、结束原因与输入/输出 token，不猜测缺失的用量。
- AC-5：缺少完成事件、重复完成、完成后的额外事件与未知关键事件均安全失败。
- AC-6：超时/连接错误/429/5xx 可重试；认证/权限/非法请求/拒绝/协议错误不可重试；
  所有错误通过敏感信息泄漏测试。
- AC-7：适配器不自动重试，Python 取消信号原样传播，请求使用有限超时。
- AC-8：架构依赖测试证明 core 不导入 OpenAI SDK，共用接口测试不接触网络或 API key。
- AC-9：JSON Schema 快照、Ruff、Pyright、完整 pytest、文档检查、站点构建、安装包与差异检查通过。

## 14. Test plan

- 单元测试：内部数据边界与不可变性、请求翻译、事件顺序、函数参数解析。
- 共用接口测试：模型服务替代实现与注入式 OpenAI 客户端共用文本/工具/完成/错误规则测试。
- 集成测试：使用 SDK 能读取的内存流验证适配器边界；默认 CI 不调用外网。
- 恢复测试：不适用；验证流式响应中途失败不生成模型完成事件，且适配器不自动重试。
- 安全测试：包含敏感信息的 SDK 错误、响应正文/响应头、格式错误的参数/元数据均不泄漏。
- 人工验证：可选的显式 API key 冒烟测试；不作为 CI 或 Feature 完成的必要条件。

## 15. Documentation impact

- [x] Engineering source of truth (`docs/`)
- [x] Site beginner learning path
- [x] Site developer documentation
- [x] Site current status / milestone summary
- [x] Architecture / ADR
- [x] Deployment docs：无部署入口变化，记录为不适用。
- [x] Generated reference：公共 JSON Schema 快照已同步。

## 16. Open questions

无。ContextBuilder/Loop 已拆分到 F-0016；F-0004 使用 Responses HTTP 流式响应，并保持单一
生产适配器。
