---
title: "ADR-0015: user configuration selects explicit model protocol adapters"
status: accepted
date: 2026-08-22
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0015：用户配置显式选择模型协议 adapter

## 要解决的问题

用户购买的模型服务不一定提供同一种 API。OpenAI Responses、OpenAI Chat Completions 和 Anthropic
Messages 的请求、流式事件、ToolCall、usage 与错误格式不同。当前 `bootstrap.py` 始终创建
`OpenAIResponsesProvider()`，所以用户即使已有其他服务的 key，也只能修改代码。

按厂商增加 `DeepSeekProvider`、`OpenAIProvider`、`ClaudeProvider` 会把品牌扩散到 Runtime，同一厂商
支持多个 protocol 时命名也会失真。把所有服务称为“OpenAI-compatible”并自动试 endpoint，又可能在认证
或协议失败时把 key 发给错误目标、产生隐藏费用。

F-0004/ADR-0010 已选择 Responses 作为首个 adapter，并保留 Provider-neutral port。现在需要决定第二、
第三个 adapter 怎样进入 production composition，以及本地配置怎样直接可用而不把 secret 带入运行记录。

## 选择时最看重什么

- 可维护性：每个 wire protocol 的翻译集中在一个 adapter，Runtime 不出现厂商分支；
- 恢复语义：协议或认证失败不能静默重发到另一个 endpoint，每次调用仍对应一个 Activity；
- 安全：key 只交给用户显式选择的 endpoint，且不进入 Event、日志、错误或报告；
- 复杂度/交付时间：复用现有 port/OpenAI SDK，不引入聚合框架或 DI container；
- 兼容与迁移：旧 RunProfile/Event/SQLite 可读，新协议运行同一组 contract。

## 比较过的方案

### 方案 A：每个厂商一个 adapter

容易上手，但品牌和模型会快速增加；同一 protocol 被重复实现；Runtime/CLI 会出现厂商分支。

### 方案 B：一个 OpenAI-compatible adapter 自动探测 endpoint

配置少，但 Responses/Chat 流式语义不同；探测产生请求和费用；认证、404 与协议损坏无法安全区分；
fallback 可能把 key 或 Prompt 发给错误 endpoint。

### 方案 C：显式 protocol adapter + 用户级 BearAgent config

用户只配置一次，Run 显式引用；翻译独立测试；调用前能明确指出选择错误；内部 port 不变。代价是用户
必须从服务文档确认 protocol，BearAgent 维护三个 adapter/schema。

### 方案 C1：catalog 只保存环境变量名

Secret 不落在 catalog 中更适合服务器部署，但本地用户必须同时编辑 JSON、创建专用环境变量并保证在
同一个 shell 中运行，首次使用路径过长。P1 是单用户本地 Runtime，因此当前选择直接 key；P3 若加入
长期服务和权限治理，再单独评估 OS secret store、环境注入或两者兼容。
### 方案 D：引入多 Provider 聚合框架

短期覆盖广，但引入大型依赖和隐式路由/重试；框架类型、兼容例外和版本节奏会主导 BearAgent 边界。

## 决定

选择方案 C：

1. `ModelProvider.stream(ModelRequest)` 与 BearAgent `ModelEvent` 是唯一内部模型接口；SDK 类型不进入
   domain、runtime、application 或 ports。
2. 首批 protocol 为 `openai_responses`、`openai_chat_completions`、`anthropic_messages`；它们是协议名，
   不是厂商 allowlist。
3. Responses/Chat adapter 使用现有官方 OpenAI Python SDK；Messages adapter 使用官方 Anthropic Python
   SDK。SDK 锁定兼容版本、关闭自动重试，只存在于 `adapters/model/`。
4. `data/config.json` 保存严格 Provider config：`provider_id`、面向用户的厂商 `name`、protocol、HTTPS
   base URL、直接填写的 `api_key`、显式 model 列表和 `default_model`；不包含 pricing、Tool 或权限。
5. `api_key` 使用 `SecretStr`，配置错误隐藏原始输入；config 必须被 Git 忽略。Key 只在 composition
   root 解封并交给选中 adapter，不进入 Event、日志、CLI 输出、错误或 live report。Config 不接受
   objective、workspace、Prompt、模型或 Tool 覆盖。
6. `RunProfile v2` 通过 `provider_id` 选择条目，不重复保存 model/pricing；bootstrap 从 Provider 默认模型
   构造 `unpriced` 的内部 `AgentConfig`。真实 gate 单独注入版本化 pricing 快照；Event、预算和 Context
   仍保存一次 Run 的精确模型快照；v1 保留 legacy Responses 环境配置兼容。
7. `bootstrap.py` 是唯一 selector；按 protocol 精确创建 adapter，不按厂商、model、URL 猜测或 fallback。
8. 新 `RunCreated v3` 保存 `provider_id`、由非密钥 Provider/model 配置计算的 `config_version`、
   `protocol`，不保存 base URL、key
   或 SDK client；Runtime 只携带/保存，不按 protocol 分支。
9. adapter 只实现文本、client-side function tools、流式增量、完整 ToolCall、usage、finish reason、
   request identity 和安全错误；Provider 托管 Tool、服务端会话、多模态和自动重试不在范围内。
10. Compatibility 由 contract 判定。缺 usage、未知关键 event、completion 损坏或 ToolCall 不一致时失败，
    不猜测或换协议。
11. Chat adapter 在外部 wire 边界把不符合 function name 约束的内部 Tool 名称确定性映射为安全别名，
    Provider 返回后再恢复；Runtime、Policy 和 Event 始终使用内部名称。Tool 参数仍由 BearAgent 校验，
    不依赖 Provider 特有的严格模式。
12. Model 条目可对 Chat Completions 显式选择 `thinking_mode: "disabled"`；默认值仍是
    `provider_default`。P1 不保存隐藏推理，adapter 收到无法安全表示的非空 reasoning 时失败，不能静默
    丢弃或写入 Event。
13. P1 live gate 可使用任一受支持配置；一次真实成功不证明其他服务或协议已付费联调。
14. 自动模型发现不属于 catalog 加载。OpenCode 等工具只对已知 Ollama、LM Studio、vLLM 集成自动发现，
    Cline、Continue、OpenHands 和普通自定义 Provider 仍要求显式 Model ID。未来如加入 `models refresh`，
    必须由用户触发且不能把目录结果当作 ToolCall、streaming、usage、limit 或价格兼容证明。

用户字段选择参考了以下官方配置文档：

- [OpenCode Providers](https://opencode.ai/docs/providers/)
- [OpenCode Models](https://opencode.ai/v2/docs/models)
- [Continue config.yaml Reference](https://docs.continue.dev/reference)
- [Cline OpenAI Compatible](https://github.com/cline/cline/blob/main/docs/provider-config/openai-compatible.mdx)
- [OpenHands CLI configuration](https://docs.openhands.dev/openhands/usage/cli/command-reference)

ADR-0015 扩展而不替代 ADR-0010。ADR-0010 的首个 adapter、无隐式重试、SDK 隔离和安全错误决定继续有效。

官方协议依据：

- [OpenAI Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [OpenAI Chat Completions API](https://developers.openai.com/api/reference/resources/chat/completions/methods/create)
- [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages/create)

## 带来的影响

### 得到的好处

- 用户配置已有服务，不等待厂商品牌分支；
- 已支持 wire protocol 的新服务通常只需 catalog 条目；
- 真正的新 protocol 通过 adapter 接入，Runtime/Tool/Policy/EventStore/AgentLoop 不变；
- 明确选择避免探测/fallback 的 key 错发、隐藏请求和费用；
- Run 保存非敏感 Provider 选择，inspect/eval 能解释配置。

### 接受的代价

- 用户要从服务文档确认 protocol、base URL 和 model；
- 增加 Anthropic SDK、两个 adapter 及其升级测试成本；
- compatible 服务可能缺 usage 或 streaming 不标准，届时明确失败；
- config v1、RunProfile v2、Event v3 成为版本化契约；config 文件本身成为必须受保护的敏感文件；
- P1 只提供 JSON 配置，不提供 P4 级配置向导或在线目录。

## 迁移和回退

`RunProfile v1` 继续映射 legacy Responses，使用 `OPENAI_API_KEY` 和可选 `OPENAI_BASE_URL`。Config v1
直接保存 key，新文档和 live gate 使用 v2 + config。Event v1/v2 与 SQLite schema v1 可读；Event v3
仍写现有 payload JSON，
无需 SQL migration。

可停止暴露 v2/catalog 并删除未使用的新 adapter，但写入 Event v3 后必须保留读取兼容。不得删除用户
数据库、Run、Artifact 或 `outputs/**`。只有 Messages adapter 完全移除且 lock/build/wheel 通过后才删除
Anthropic SDK。

## 怎样验证

- catalog/RunProfile v1/v2 的 schema、大小、link、TOCTOU、URL、SecretStr 和 secret redaction 测试；
- Fake、Responses、Chat、Messages 共享文本、ToolCall、usage、completion、error、timeout、cancel、
  no-retry contract；
- adapter 使用 mock transport/注入 client，默认 CI 不联网；
- import boundary 证明 SDK 不越过 `adapters/model/`，bootstrap 是唯一 selector；
- Event v1/v2/v3、Reducer、SQLite、query 回归；
- secret、authorization、base URL、原始异常和跨 endpoint fallback 安全测试；
- 项目所有者显式授权一项真实配置完成 P1 live gate；
- 聚合框架若未来能在不接管重试、路由、类型和错误语义的前提下降低成本，再单独 ADR。
