---
title: "ADR-0014: CLI calls application commands while production wiring stays in bootstrap"
status: accepted
date: 2026-08-20
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0014：CLI 只调用 application command，生产依赖只在 bootstrap 组装

## 要解决的问题

F-0005 需要把 `AgentLoop`、OpenAI Responses adapter、SQLite Store、四个 workspace Tool 和固定 Policy
接到 Typer CLI，还要让 inspect/events 读取同一批事实。最短的写法是让每个 CLI handler 自己创建
adapter、读取 SQLite 或拼装 JSON；这样执行、查询和未来 HTTP API 会逐渐形成不同业务路径，测试也只能
通过 Typer 才能调用核心用例。

另一个冲突是配置边界。`AgentConfig` 和预算需要版本化保存，Provider key/base URL 与本机路径却不能
进入 Event。如果 CLI 把所有参数混成一个自由字典，application 很难分清哪些是可保存事实、哪些只能
留在 composition root。

现在必须统一三件事：具体 adapter 在哪里创建、执行/查询由哪个模块负责，以及 human/JSON 输出共享
什么 Provider-neutral 结果。

## 选择时最看重什么

- 可维护性：执行和查询可以脱离 Typer 测试，未来接口不用复制业务规则；
- 恢复语义：inspect/events 只相信 EventStore 与 Reducer projection，不解析日志或 adapter 状态；
- 安全：凭据、endpoint、本机绝对路径和原始异常停在最外层，Tool 不能旁路 Policy；
- 复杂度/交付时间：复用现有 ports 和 Pydantic 类型，不引入 DI framework、服务容器或数据库 ORM；
- 兼容与迁移：保持现有 AgentLoop、Event v1/v2 和 SQLite schema v1 可读。

## 比较过的方案

### 方案 A：Typer handler 直接组装 adapter 并查询 SQLite

代码最少，命令参数可以直接传给 SDK/SQLite。但 CLI 会同时承担配置、业务协调、SQL、错误转换和展示；
human/JSON 很容易各查一次，未来 HTTP API 也只能复制同样逻辑。SQLite row、OpenAI client 或 Typer 类型
还可能进入 application/runtime，破坏现有依赖方向。

### 方案 B：application command 管用例，bootstrap 组装具体 adapter，CLI 只输入和渲染

`bootstrap.py` 是唯一知道 OpenAI、SQLite 和 workspace adapter 的 composition root。application command
只接收 BearAgent 类型和 ports，执行 AgentLoop 或查询 EventStore，并返回冻结、可序列化的结果。CLI
只验证系统边界输入、选择 human/JSON renderer 和退出码。代价是增加少量 application DTO/query service
和组装代码。

### 方案 C：引入服务容器、配置框架或 workflow framework

自动注入和多环境配置会更方便，但 P1 只有一个本地进程、一个 Provider 和一个 CLI。框架不能替代
BearAgent 自己的 Event、Policy、预算和失败语义，反而增加生命周期与隐式全局状态。

## 决定

选择方案 B，并作出以下约束：

1. `src/bearagent/bootstrap.py` 是生产 composition root。具体 `OpenAIResponsesProvider`、
   `SqliteEventStore`、workspace Tool、Registry、FixedToolPolicy、ToolExecutor 和 AgentLoop 只能在外层
   组装；bootstrap 不实现状态、预算、Policy 或查询规则。
2. `interfaces/cli` 只解析 CLI/profile 输入、调用 application command、渲染 human/JSON 和映射退出码。
   它不得执行 SQL、直接调用 Tool、解析 Provider SDK response 或从日志推断状态。
3. application 增加 Provider-neutral Run command/query service。inspect 使用 `EventStore.get_run` 与
   有界 `list_events`；events 使用同一 port 的分页接口。不存在第二套 projection 或 Artifact 数据库。
4. application 与 CLI 之间只交换 BearAgent Pydantic 类型，例如 `RunResult`、`RunInspection`、
   `EventPage` 和安全 command error。JSON schema version 由公开结果定义，human renderer 读取同一对象。
5. 非敏感运行配置使用严格、有 byte 上限的 version 1 JSON Run profile，内容仅为 `AgentConfig` 和
   `BudgetLimits`。profile 完整校验后才初始化数据库或 Provider。
6. API key、可选 base URL、database path 和 workspace root 属于 production configuration，不进入
   Run profile、AgentConfig 或 Event。CLI 不接受 `--api-key`；Provider 凭据从受信任进程环境注入。
7. Tool registry 可以包含四个 P1 workspace Tool；profile 的 Tool 名单同时限制模型可见 schema 和
   FixedToolPolicy allowlist，但不能改变 Policy 对危险 side effect 的硬拒绝。
8. CLI 保持路线图语法：`bearagent run <objective>` 是 run command group 的无子命令执行路径；同组
   `inspect/events` 调用 query service。CLI 结构只是接口层规则，不进入 Runtime。
9. 运行命令可以在最外层预生成 RunId，并传给 AgentLoop，以便在第一次 Provider 调用前让用户看到
   可查询 ID；不传时 AgentLoop 保持现有内部生成行为。RunId 不由模型或 profile 指定。
10. 不增加生产依赖、SQLite migration、后台服务、service locator 或可变全局 container。
11. F-0005 可以组装 ADR-0010 已接受的 OpenAI Responses adapter，但 Feature 验证只注入 Fake Provider，
    不读取真实凭据、不发起真实模型请求。是否把真实模型演练列为 P1 退出条件，在 F-0005 完成后另议。

## 带来的影响

### 得到的好处

- Fake/真实 Provider、临时/真实 SQLite 都能复用相同 application command 测试；
- CLI、未来 HTTP API 和开发者 Python 调用可以共享执行/query 结果，不复制 SQL、Reducer 或状态判断；
- SDK、数据库和文件 adapter 继续停在外层，domain/runtime/application 保持可测试；
- profile 可以随 RunCreated 保存可复现配置，而凭据和本机路径不会进入 Event；
- query 可以明确区分 projection、完整 Event payload 和有限 human 摘要。

### 接受的代价

- `bootstrap.py` 从占位文件变成显式组装模块，需要窄接口与集成测试防止它膨胀；
- CLI 需要独立的 renderer、错误 envelope 和 schema version，公开后不能随意改字段；
- inspect 为提取 Artifact 需要有界分页读取 Event；超出可信上限时必须失败，而不是返回假完整结果；
- run command group 的“无子命令执行 + inspect/events 子命令”需要专门 CLI 解析回归测试；
- profile 是一个额外准备步骤，但它避免硬编码会漂移的模型价格或把大量配置塞进命令历史。

## 迁移和回退

F-0005 不改变 SQLite schema 或 Event payload。已有 v1/v2 数据可直接通过新 query service 读取。CLI
JSON 在首次发布前可随 draft 调整；发布后不兼容变化使用新 schema version。

回退时移除新 CLI/application/bootstrap 代码和未发布 profile 示例即可。不得删除用户数据库、
`outputs/**` 或 v2 读取兼容。若 AgentLoop 已增加可选预生成 RunId，回退 CLI 时可保留这个兼容参数；
它不改变已保存 Event 语义。

## 怎样验证

- application command 使用 Fake Provider/InMemory Store 与 Fake Provider/SQLite 独立于 Typer 运行；
- CLI integration 证明 human/JSON 调用同一 command result，且每个 JSON stdout 只有一个对象；
- import boundary 测试禁止 domain/runtime/application 导入 Typer、OpenAI、SQLite 和 workspace adapter；
- spy/fixture 证明 CLI/bootstrapping 不直接执行 Tool，所有文件动作经过 FixedToolPolicy + ToolExecutor；
- query tests 证明只调用 EventStore port、分页有界、缺失/损坏数据安全失败，不执行自定义 SQL；
- profile/错误输出扫描确认 key、authorization、base URL、本机绝对路径和原始异常没有进入 Event/JSON；
- console script、`python -m bearagent`、wheel import 和 Windows/Ubuntu 测试通过；
- 项目所有者接受本决定后，F-0005 Plan 才能激活并开始实现。

项目所有者于 2026-08-20 接受本决定，并明确把真实模型 API/演练留到 F-0005 完成后讨论。
