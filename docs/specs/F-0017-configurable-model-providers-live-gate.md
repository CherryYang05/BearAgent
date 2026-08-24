---
title: "Feature: configurable model service protocols and P1 live-model gate"
status: implemented
spec_id: F-0017
milestone: P1
owner: CherryYang05
created: 2026-08-22
last_updated: 2026-08-25
implemented_in: "codex/F-0017-p1-live-model-gate"
related_adrs: [ADR-0004, ADR-0007, ADR-0009, ADR-0010, ADR-0013, ADR-0014, ADR-0015]
---

# F-0017：配置自己的模型服务，并用真实模型完成可检查文件任务

## 1. 为什么现在要做

用户期望只配置一次自己购买的模型服务，然后反复运行不同目标：

```powershell
bearagent run "阅读 docs，并把总结写到 outputs/summary.md"
bearagent run "比较两份设计，并把差异写到 outputs/diff.md"
```

当前 `RunProfile` 只保存 Agent 和预算，`bootstrap.py` 则始终创建
`OpenAIResponsesProvider()`。只提供 OpenAI Chat Completions 或 Anthropic Messages 的服务，即使用户
已经购买 API，也必须修改代码。把当前使用的 DeepSeek 写死到 Runtime，同样不能解决这个问题。

F-0004 已建立 Provider-neutral `ModelProvider` port，并明确 OpenAI Responses 只是首个 adapter。
F-0017 要补齐用户级 Provider 配置和另外两种 wire adapter，再用用户选择的一项真实服务完成 P1
live-model gate。DeepSeek 只是一条配置和一次验收样例，不成为产品边界或专属代码分支。

## 2. 本次交付

- G-1：提供严格、有限、默认位于 `data/config.json` 的 BearAgent config v1；
- G-2：让 `RunProfile v2` 只选择 `provider_id`；config 保存厂商显示名、可用模型和默认模型，
  不再要求用户在 RunProfile 重复填写 model，也不保存易变的模型价格；
- G-3：在同一 `ModelProvider` port 后支持 `openai_responses`、`openai_chat_completions` 和
  `anthropic_messages`；
- G-4：production composition 只按显式 protocol 创建 adapter，不按厂商名分支，也不探测或 fallback；
- G-5：新 Run 保存有限、非敏感的 Provider 选择事实，旧 Run/Event 和 `RunProfile v1` 继续可读；
- G-6：三个 adapter 运行同一组 contract、安全和 production-composition 测试；
- G-7：建立默认关闭、显式费用授权的 live runner，用任一受支持配置完成固定任务 gate；
- G-8：生成脱敏报告，完成 Reality Check 和四类文档同步后关闭 P1。

## 3. 本次不做

- NG-1：不增加 `DeepSeekProvider`、`OpenAIProvider` 等按厂商命名的 Runtime 分支或预设表；
- NG-2：不声称兼容所有自称 OpenAI-compatible 或 Anthropic-compatible 的服务；
- NG-3：不自动探测 endpoint，不在失败后换协议、模型或服务，也不做路由、负载均衡或 Provider 矩阵；
- NG-4：不接入 Provider 托管的 web/file search、code interpreter、MCP、Files、Vision、批处理、
  WebSocket 或服务端会话状态；
- NG-5：除受 Git 忽略的本机 `config.json` 外，不把 API key 写入命令参数、RunProfile、Event、日志、报告或 Artifact；
- NG-6：不增加交互式配置向导、OS secret store、Provider marketplace 或在线模型发现；本次使用显式
  `models` 列表，后续 `models refresh` 才能按用户动作查询支持目录接口的服务；
- NG-7：不把真实 API 调用放进默认 pytest、CI、build、安装或 `doctor`；
- NG-8：不增加 Checkpoint、pause/resume/cancel/retry、Attempt、Receipt 或 `UNKNOWN`；
- NG-9：不使用 LLM-as-judge，也不让 Provider 配置扩大 Tool、Policy、workspace 或预算。

### 当前采用的常见配置形状与后续体验

F-0017 采用当前 Agent 工具中共同出现的概念：Provider 显示名、接口类型、base URL、API key、模型 ID
以及默认模型。一个 Provider 条目包含显式 `models` 列表和 `default_model`，但不包含 `pricing`。
普通 Run 按 `unpriced` 运行；真实费用 gate 在 preflight 中单独接收经确认的价格快照和费用上限。

官方资料显示，普通自定义云端服务通常仍要求用户填写模型 ID。自动发现主要用于 Ollama、LM Studio、
vLLM 等已知本地服务。因此在线模型发现继续后置：未来可显式执行 `models refresh` 并缓存 `/models`
候选 ID，但目录只能说明 key 能看见哪些 ID，不能证明 ToolCall、streaming、usage、上下文长度或价格
兼容；选择模型后仍需有界能力检查。

`protocol` 在 Runtime 内部仍是必要的 adapter 选择，但配置向导可为常见服务提供默认值。系统不能只按
厂商名或 URL 猜协议，因为同一服务可能同时提供 OpenAI Chat Completions 与 Anthropic Messages。
F-0017 不实现厂商目录、自动发现、能力探测、价格抓取或静默 fallback。
## 4. 需要先说明的约定

### 服务、wire protocol 和 model 是三件事

Provider service 是用户购买或部署的模型服务。Wire protocol 是 BearAgent 与服务交换 HTTP/stream
数据的格式。Model 是服务内的模型名。同一服务可能支持多个 protocol，也可能只实现其中一个。

| 协议族 | `protocol` 值 | BearAgent adapter |
|---|---|---|
| OpenAI-compatible | `openai_responses` | 现有 Responses adapter |
| OpenAI-compatible | `openai_chat_completions` | 新 Chat Completions adapter |
| Anthropic-compatible | `anthropic_messages` | 新 Messages adapter |

Responses 与 Chat Completions 的请求、流式事件、ToolCall 和 usage 结构不同，不能由一个
“OpenAI-compatible” adapter 自动猜测。

### Provider 配置一次，objective 不参与选择

`data/config.json` 是受信任的本机配置：

```json
{
  "schema_version": 1,
  "providers": [
    {
      "provider_id": "deepseek",
      "name": "DeepSeek",
      "protocol": "openai_responses",
      "base_url": "https://api.example.com",
      "api_key": "replace-with-provider-api-key",
      "models": [
        {
          "model_id": "example-chat"
        }
      ],
      "default_model": "example-chat"
    }
  ]
}
```

`RunProfile v2` 增加顶层 `provider_id`，不再保存 model 或价格。Bootstrap 从选中 Provider 的
`default_model` 解析模型，并为普通 Run 构造 `unpriced` 的内部 `AgentConfig`。不同 objective 复用这两份
配置；只有切换服务、默认模型、Agent 或预算时才修改。

`config.json` 直接保存本机 API key。该文件必须被 Git 忽略，并只由用户在受信任的本机编辑。BearAgent 使用
`SecretStr` 在内存和错误中遮蔽 key；Objective、workspace、模型和 Tool 输出都不能读取、修改或选择
Provider 配置。

### 协议兼容是严格受测子集

三个 adapter 只支持当前需要的文本、client-side function tools、流式增量、完整 ToolCall、finish
reason、usage、request identity 和安全错误。缺少 usage、未知关键事件或完成时改变 ToolCall 都明确
失败，不猜测、不换协议。

离线 contract tests 覆盖三个 adapter。P1 退出只要求用户选择其中一个真实配置完成整套 gate，不要求
分别向 OpenAI、Anthropic 和第三方服务付费。一次成功不能扩大成全市场兼容结论。

## 5. 使用场景

### 5.1 配置一次后运行不同目标

用户创建 `config.json`，并在 `RunProfile v2` 中选择 `provider_id`。之后 CLI 每次解析同一份
config/profile，用户不需要为每个问题生成 Provider JSON，也不在命令中传 key。

### 5.2 用户的服务只支持另一种 protocol

服务支持 Chat Completions 时选择 `openai_chat_completions`；支持 Anthropic Messages 时选择
`anthropic_messages`。AgentLoop、Tool、Policy、EventStore 和 CLI 不变，只有 bootstrap 创建的
adapter 不同。

### 5.3 配置错误时不静默尝试其他服务

`provider_id` 不存在、protocol 未知、base URL 非法或 key 未配置时，BearAgent 返回有限错误。它不把
Responses 请求改成 Chat Completions，不把一个服务的 key 发给另一个 endpoint，也不扫描本机配置猜测。

### 5.4 执行真实模型 gate

项目所有者先运行 preflight，确认公开 fixture、Provider、model、定价快照和 suite 最大估算费用。授权
后，runner 为五个任务创建隔离 workspace 和 SQLite，通过 production `build_run_services` 执行且不
注入 Fake Provider。完成后重开数据库，通过 `RunQueryService.inspect/events` 核对结果。

## 6. 必须满足的行为

### 6.1 BearAgent config 和 RunProfile

- FR-1：`config.json` 必须是 schema v1、有限大小、UTF-8、拒绝未知字段的 JSON，最多 32 个
  `provider_id` 唯一条目；
- FR-2：条目包含有界 `provider_id`、Provider `name`、三选一 protocol、绝对 HTTPS base URL、非空
  `api_key`、1 至 128 个 model 和指向其中一项的 `default_model`，且拒绝 `pricing`；model 可显式声明
  `thinking_mode`，非默认值 `disabled` 只允许用于 Chat Completions；URL 禁止 userinfo、query 和 fragment；
- FR-3：catalog/profile 按普通文件边界读取，拒绝 link、特殊/超大/非 UTF-8 文件、读取期间替换和未知字段；
- FR-4：`RunProfile v2` 必须包含 `provider_id`，且只能选择 config 条目；它不接受 model 或 pricing，
  bootstrap 必须从 Provider 的默认模型构造 `unpriced` 的内部 `AgentConfig`；
- FR-5：`RunProfile v1` 继续映射到使用 `OPENAI_API_KEY`、可选 `OPENAI_BASE_URL` 和
  `openai_responses` 的 legacy selection；新示例和 live gate 使用 v2；
- FR-6：catalog/profile 结构、引用或 key 错误在创建数据库和 Run 前失败；live preflight 同样在首个
  Run 前拒绝且零调用；
- FR-7：key 值只从选中条目的 `api_key` 读取并直接传给 adapter；配置模型使用 `SecretStr`，key
  不进入异常、日志、Event、CLI JSON、report 或命令历史。

### 6.2 三种 adapter 共享一个内部接口

- FR-8：adapter factory 只接受三个已声明 protocol；未知值失败，不按厂商名或 URL 推断；
- FR-9：三个 adapter 都实现 `ModelProvider.stream(ModelRequest)`，只返回 BearAgent `ModelEvent`；
  SDK/HTTP response 类型只能停留在 `adapters/model/`；
- FR-10：adapter 翻译 system/user/assistant/tool Message、function Tool schema、文本增量、完整单/多
  ToolCall、finish reason、request ID、实际 model 和 input/output usage；Chat adapter 在 wire 边界把内部 Tool
  名称映射为协议允许的别名，并在返回时恢复，Runtime 和 Event 不保存别名；
- FR-11：Provider 完成但没有必需 usage 时返回 `provider_protocol_error`，不得按字符或 tokenizer 猜测；
- FR-12：SDK 自动重试关闭；adapter 不自动重发；`CancelledError` 原样传播，timeout/错误映射到现有
  安全 `ErrorInfo`；
- FR-13：adapter 不使用 Provider 托管 Tool 或服务端会话。每次发送 Event 重建的完整有界 Context，只
  暴露 workspace function tools；
- FR-14：只有文档明确且不影响文本/ToolCall/completion 的 lifecycle event 可以被明确忽略；未知关键
  event、重复/缺少 completion、流后事件、ToolCall 不一致和无法安全表示的非空隐藏 reasoning 都失败；
  BearAgent 不持久化或回放隐藏 reasoning；
- FR-15：一次返回多个 ToolCall 时全部翻译；AgentLoop 仍逐个检查预算、Policy 和 WorkspaceBoundary 后
  串行执行。Provider parallel 参数不是安全边界；
- FR-16：`bootstrap.py` 是唯一 production selector。正常 CLI/live runner 不注入 Provider；测试保留
  Fake 和 client 注入 seam。

### 6.3 Provider 选择属于可检查事实

- FR-17：新 Run 使用 Event schema v3；`RunCreated` 保存有限 Provider selection：
  `provider_id`、由非密钥 Provider/model 配置自动计算的 `config_version`、`protocol`；AgentLoop 只保存，
  不按 protocol 分支；
- FR-18：Run/Event 不保存 base URL、key、SDK client、HTTP header 或 catalog 路径；
- FR-19：Reducer、SQLite、query 和 schema registry 继续读取 Event v1/v2；v3 不改写旧 Event 或旧状态含义；
- FR-20：SQLite 继续保存版本化 payload JSON，不增加 table/column migration；`inspect/events` 展示
  Provider selection 的有限摘要。

### 6.4 Live gate 和 P1 关闭

- FR-21：只有显式 opt-in、合法 catalog/RunProfile v2、存在的 key、非零预算和 suite cost cap 同时存在，
  才创建首个 Run；
- FR-22：五个 versioned task 继续位于 `evals/p1/`；Fake/真实模型读取同一 objective、fixture、预算和
  rubric；`replace-existing-output` 增加模型可读的批准内容来源；
- FR-23：每个任务使用独立临时 workspace、SQLite 和收紧的 profile；任务只能缩小 Tool/预算，不能改变
  Provider selection；
- FR-24：runner 只经 production composition 执行。完成后重开数据库，只通过 application query service
  检查 projection、Event 和 Artifact；
- FR-25：API 调用前显示有限 Provider 身份、model、任务和最坏估算费用；费用标为 Runtime estimate；
- FR-26：四个正常任务必须全部通过确定性 rubric；安全任务必须满足 canary 未泄露和无成功越界读取；
- FR-27：措辞和 Tool 顺序可以变化；事实、路径、hash、终态、Tool 名称和 canary 用代码判断，不用隐藏
  答案或 LLM-as-judge；
- FR-28：失败不自动重试；再次运行创建新的本地 attempt/report，不覆盖旧证据；
- FR-29：每次 attempt 原子生成脱敏 report v1，包含 provider selection、版本、commit、model、Run ID、
  终态、Error、usage、估算费用、Tool、Artifact、rubric、Reality Check 和总体 verdict；
- FR-30：live gate、Reality Check 和文档同步全部通过后，才关闭 F-0017/P1。

## 7. 对外入口和模块连接

```text
bearagent run OBJECTIVE
```

CLI 默认读取 `data/p1-run-profile.json` 和 `data/config.json`；只有临时使用其他文件时才需要用
`--profile` 或 `--config` 覆盖。CLI 不增加 `--api-key`、`--protocol`、`--base-url` 或厂商专属参数。

```text
RunProfile v2 --provider_id--┐
                             ├-> bootstrap 选择 Provider entry
BearAgent config ------------┘              |
                                            v
                              explicit protocol factory
                                            |
                                            v
                                  ModelProvider port
                                            |
                                            v
                         AgentLoop -> Tool/Policy/EventStore
```

`build_run_services` 增加 catalog 输入和显式 factory。选择只在 composition root；port、AgentLoop 和
query service 保持 Provider-neutral。验收入口 `scripts/run_p1_live_eval.py` 复用同一 catalog/profile
和 production composition，不另写选择或执行逻辑。

## 8. 状态和保存的数据

新 Run 使用 Event v3；相对 v2，只有 `RunCreated` 增加有限 Provider selection，其余状态、Activity、
预算、模型和 Tool 事实不变。SQLite schema v1 无 migration。

`RunProfile v1` 与 Event v1/v2 继续读取。`config.json` 是本机运行配置；Event 只保存选中条目的
非敏感身份和版本。条目的非密钥连接、模型或价格配置变化时，bootstrap 自动计算新的 `config_version`；API key 轮换不改变
该审计身份，用户不需要维护版本字段。

Live evidence 目录保存数据库、临时 workspace 和完整输出，并由 `.gitignore` 排除。脱敏 report 是派生
验收证据，不参与恢复。

## 9. 失败时会发生什么

- catalog/profile 损坏、引用不存在或 protocol 非法：Run 前返回 `invalid_input`；
- key 缺失、空白或格式非法：普通 Run 与 live preflight 都在创建数据库和首个 Run 前失败且零调用；
- 认证、限流、连接或 timeout：返回有限 Provider Error，不打印 endpoint/key；
- 服务不满足 protocol、completion/usage 缺失：`provider_protocol_error`，不换 adapter；
- 多 ToolCall 中任一预算/Policy 失败：保存已有事实，后续未开始 Tool 不执行；
- Artifact/rubric/hash/重开查询失败：总体 gate 失败；
- Ctrl+C 保留已提交 Event，不自动 resume 或伪造 terminal；
- report 写入失败不改变 Run，临时文件不能作为通过证据。

## 10. 安全与隐私

- catalog/profile 是受信任配置，但按敌对字节解析，不能由模型可写路径或 objective 覆盖；
- `config.json` 直接保存 key，因此文件必须被 Git 忽略；key 只在内存中交给选中的 adapter；
- base URL 必须显式 HTTPS，禁止 userinfo/query/fragment；客户端不得跨 origin 跟随重定向；
- 配置、错误、CLI JSON、Event、Artifact 和 report 扫描 secret、authorization、base URL 和绝对路径；
- SDK response、模型和 Tool 输出不可信，不能授予权限；
- 所有 Tool 继续经过 Registry、prepare、FixedToolPolicy、ToolExecutor 和 WorkspaceBoundary；
- Provider 托管 Tool 不进入请求；
- live gate 只发送公开 fixture，不发送用户仓库、`.env`、`data/` 或 secret；
- 真实调用前再次显示 Provider、公开数据范围和费用上限，并取得明确授权。

## 11. 怎样检查执行过程

新 Run 的 `inspect/events` 显示 `provider_id`、`config_version`、`protocol` 和实际 model 的有限摘要，
不显示 base URL 或 key。

Live report 说明实际配置、调用的 Tool、Artifact 路径/hash、失败层级，以及为什么 P1 可以或不能关闭。

## 12. 上线与回退

上线顺序：

1. catalog/RunProfile v2、v1 兼容和 Event v3；
2. 扩展现有 Responses contract；
3. Chat Completions 与 Anthropic Messages adapter/mock transport；
4. bootstrap/CLI selector 和 production-composition 测试；
5. Fake runner、rubric、report 和失败门；
6. 项目所有者另行提供 key、model、定价和费用授权，执行真实 gate；
7. Reality Check、文档同步和 P1 关闭。

回退保留 RunProfile v1、旧 Event、SQLite 和 `outputs/**`。可停止发布 v2/catalog 和新 adapter，但已写入
Event v3 必须继续可读。只有 Messages adapter 移除且 lock/build/wheel 验证通过后才能删除 Anthropic SDK。

## 13. 验收标准

- AC-1：一个 config/RunProfile v2 可连续运行不同 objective；config 可以为一个厂商保存多个 model 和
  一个默认 model，不接受 pricing，RunProfile 不重复保存 model，也不在命令中传 key；
- AC-2：三个 protocol 创建正确 adapter，不存在针对厂商的 Runtime 分支；
- AC-3：未知 protocol、缺 provider/key、重复条目、非法 URL 和 link-like 文件在调用前失败；
- AC-4：Responses、Chat Completions、Messages 与 Fake 共享文本、单/多 ToolCall、usage、finish、错误、
  取消和 no-retry contract；Chat 的内部 Tool 名称完成 wire-safe 往返，显式关闭 thinking 时请求体准确；
- AC-5：adapter 不泄漏 SDK 类型、key、authorization、base URL、原始错误或响应正文；
- AC-6：v3 Provider selection 可查；Event v1/v2、RunProfile v1 和 SQLite 无迁移回归通过；
- AC-7：多 ToolCall 串行执行，每个 Tool 前重新检查预算和 Policy；
- AC-8：缺 usage、未知关键 event、无法安全表示的非空隐藏 reasoning、ToolCall 改变、重复/缺 completion 时
  失败，不猜测/fallback；
- AC-9：live preflight 缺任一前置条件时数据库、workspace 和 Provider 调用均为零；
- AC-10：live runner 只经 production composition；四个正常任务和安全 canary gate 全部通过，SQLite 重开
  后 inspection/Event/Artifact 一致；
- AC-11：每次 attempt 生成独立、原子、脱敏 report；失败/incomplete 不生成 `passed`；
- AC-12：默认 pytest、CI、build、wheel smoke 和 `doctor` 不读 key、不联网，现有 Fake task 继续 5/5；
- AC-13：Ruff、Pyright、pytest、schema、docs、Starlight、sdist/wheel 和隔离安装 smoke 通过；
- AC-14：只有全部 gate 和四类文档同步通过后 F-0017/P1 才完成；
- AC-15：最终状态明确 P1 不支持 P2 的恢复、Attempt、控制命令和 `UNKNOWN`。

## 14. 验证方式

- Unit：catalog/RunProfile v1/v2、selection、URL/key、factory、rubric、report 和费用 preflight；
- Contract：Fake + 三种 production adapter 的共享行为，以及三种 wire fixture；
- Integration：mock transport、bootstrap/CLI selector、Fake live runner、SQLite 重开；
- Recovery：Event v1/v2/v3、流中断、部分 ToolCall、原子 report 失败；不实现自动恢复；
- Security：secret/base URL/raw error、配置 link/TOCTOU、恶意 SDK payload、canary；
- Eval/manual：任一受支持真实配置完成四个正常任务和一个强制安全任务；
- Build/docs：lock、Ruff、Pyright、pytest、schema、docs、Starlight、sdist/wheel、隔离 CLI smoke。

## 15. 文档同步

- [ ] Engineering source of truth：Spec、ADR、Plan、Architecture、Roadmap、P1 outcome 和脱敏报告；
- [ ] Site beginner：Provider/协议/model 区别，配置一次后运行多个 objective；
- [ ] Site developer：catalog、factory、三种翻译边界、Event v3 和 secret 边界；
- [ ] Site current status / milestone summary：全部 gate 通过后才把 P1 改为完成；
- [ ] Architecture / ADR：从“首个 adapter”更新为“显式协议 adapter”，不把服务商写成产品边界；
- [ ] Deployment docs：本地敏感 catalog、HTTPS endpoint 和费用提示；
- [ ] Generated reference：config v1、RunProfile v2、Event v3、report v1 schema/example。

## 16. 已确认但延后提供的真实调用参数

- D-1：真实验收使用的 API key、model、pricing snapshot 和 suite cost cap 在真实 preflight 前由项目所有者确认；
  这些参数不阻塞配置、adapter、离线测试和 runner 实现；
- D-2：2026-08-23 的 suite v1.1.1 真实 gate 已通过；四个普通任务与安全 canary 全部满足确定性检查。
  脱敏证据见 [F-0017 P1 live report v1](../evidence/F-0017-p1-live-report-v1.json)，不包含完整输出、Event、
  base URL 或 secret。
