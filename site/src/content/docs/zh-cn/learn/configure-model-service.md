---
title: 配置一次模型服务，运行不同目标
description: 在 config.json 填写厂商、URL、API key、模型列表和默认模型。
bearStatus: implemented
sourceRefs:
  - F-0017
  - ADR-0015
  - F-0005
---

你不需要为每个问题生成一份 Provider JSON。下面两次运行复用同一份 `config.json` 和 RunProfile；
变化的只有 objective：

```powershell
bearagent run "阅读 docs，并把总结写到 outputs/summary.md"
bearagent run "比较两份设计，并把差异写到 outputs/diff.md"
```

## 先分清服务、protocol 和 model

- Provider service 是你购买或部署的模型服务；
- protocol 是这个服务接收和返回的 HTTP/stream 格式；
- model 是该服务中的模型名。

“兼容 OpenAI”还不够精确。Responses 与 Chat Completions 的请求、ToolCall 和流事件不同。BearAgent
当前实现三个 protocol：

| `protocol` | adapter |
|---|---|
| `openai_responses` | OpenAI Responses wire adapter |
| `openai_chat_completions` | OpenAI Chat Completions wire adapter |
| `anthropic_messages` | Anthropic Messages wire adapter |

这些值表示协议，不是厂商名单。同一厂商也可能提供多个协议，所以 BearAgent 不根据 URL、model 或
错误自动猜测，也不会失败后把同一个 Prompt 和 key 发到另一条 endpoint。

## 第一步：在本机配置服务和 key

复制 [config 示例](https://github.com/CherryYang05/BearAgent/blob/main/config.example.json)
到 `data/config.json`，再填写服务提供方给出的值：

```json
{
  "schema_version": 1,
  "providers": [
    {
      "provider_id": "deepseek",
      "name": "DeepSeek",
      "protocol": "openai_chat_completions",
      "base_url": "https://api.deepseek.com",
      "api_key": "在这里填写真实API Key",
      "models": [
        {
          "model_id": "填写服务实际支持的模型ID",
          "name": "可选的模型显示名",
          "thinking_mode": "disabled"
        }
      ],
      "default_model": "填写服务实际支持的模型ID"
    }
  ]
}
```

`data/config.json` 已被 Git 忽略，但它现在是敏感文件：不要提交、截图、复制到 issue，或把它放进
模型可写的 `outputs/**`。BearAgent 用 `SecretStr` 遮蔽内存模型和校验错误中的 key；Event、CLI 输出、
SQLite 和 live report 都不保存 key。base URL 必须是没有账号、query 或 fragment 的绝对 HTTPS URL。

这些字段分别做一件事：

| 字段 | 含义 |
|---|---|
| `provider_id` | BearAgent 本地引用这个服务的稳定 ID |
| `name` | 给人看的厂商或服务名称 |
| `protocol` | 选择实际 wire adapter，不能只靠 URL 猜 |
| `base_url` | 服务 API 的 HTTPS 根地址 |
| `api_key` | 该服务的本机密钥 |
| `models` | 同一个 URL/key 下允许使用的模型 |
| `default_model` | 普通 Run 默认选择的 `model_id` |

每个 model 最少只填 `model_id`，`name` 是可选显示名。`thinking_mode` 也可选，默认
`provider_default`；只有 Chat Completions 可显式设为 `disabled`。DeepSeek V4 默认 thinking 的 Tool
往返需要回放隐藏 reasoning，而 P1 不保存隐藏推理，因此上面的 DeepSeek 示例显式关闭 thinking。
连接配置明确不接受 `pricing`；普通 Run 使用 `unpriced`。真实 P1 live gate 单独接收版本化价格快照，
避免连接配置随价格变化。

## 第二步：RunProfile 只选择 Provider

复制 [RunProfile v2 示例](https://github.com/CherryYang05/BearAgent/blob/main/examples/run-profile-v2.example.json)
到 `data/p1-run-profile.json`。其中：

- 顶层 `provider_id` 必须与 config 中的条目一致；
- `agent_config` 只保存 Agent 指令、Context/Prompt 版本、Tool 白名单和调用限制；
- `budget_limits` 决定最多运行多少次、使用多少 token、调用多少 Tool 和最多花多少钱。

RunProfile v2 不接受 `agent_config.model` 或 `agent_config.pricing`。Bootstrap 会从 Provider 的
`default_model` 构造 `unpriced` 的内部 `AgentConfig`。公开示例故意把预算设为 0，因此只会留下可检查的
`budget_exhausted`，不会调用模型。本机 profile 可以在确认费用边界后填写非零预算。

## 第三步：运行并检查

CLI 默认读取 `data/config.json` 和 `data/p1-run-profile.json`，因此正常运行不需要重复传路径：

```console
uv run bearagent run "阅读 docs，并把总结写到 outputs/summary.md"

uv run bearagent run inspect <run-id> --json
uv run bearagent run events <run-id> --json
```

只有临时使用其他配置时，才需要用 `--config` 或 `--profile` 覆盖默认路径。

缺少、空白或非法 key 时，config 会在创建数据库和 Run 前失败。v2 Run 只用 Event schema v3 保存
`provider_id`、自动计算的 `config_version` 和 `protocol`，不会保存 base URL、key 或 HTTP header。
用户不需要手工填写 `config_version`；非密钥 Provider/model 字段变化时，它会自动变化。

Version 1 profile 仍可读取，并映射到 legacy `openai_responses` 与 `OPENAI_API_KEY`。这是已有配置的
兼容路径；新的 v2 config 使用直接填写的 `api_key`。

## P1 live gate 要单独授权

普通 `bearagent run` 只运行当前 objective。P1 live gate 会连续运行四个普通公开 fixture 和一个安全
canary，可能产生真实费用。它读取同一份本机 config，不在命令中传 key：

```powershell
$confirmedModel = Read-Host "Confirmed model"
$confirmedPricingVersion = Read-Host "Confirmed pricing version"
$inputRate = Read-Host "Input micro-USD per million tokens"
$outputRate = Read-Host "Output micro-USD per million tokens"
$confirmedCostCapMicrousd = Read-Host "Maximum suite cost in micro-USD"
$commit = (git rev-parse HEAD).Trim()

uv run python scripts/run_p1_live_eval.py `
  --allow-live-api `
  --expect-provider-id primary `
  --expect-model $confirmedModel `
  --expect-pricing-version $confirmedPricingVersion `
  --input-microusd-per-million-tokens $inputRate `
  --output-microusd-per-million-tokens $outputRate `
  --commit $commit `
  --max-suite-cost-microusd $confirmedCostCapMicrousd
```

Preflight 先核对 config/profile、key、五个公开 fixture、model、独立 pricing 快照、commit、非零预算和
Runtime 最坏费用估算。任一条件不符时，不创建数据库、workspace、SDK client 或 Run。Preflight 把已
校验的 config 保留在内存中交给 production factory，不额外复制一份包含 key 的临时配置文件。

## 多模型已经可配，自动发现仍后置

现在一个 Provider 已经可以显式列出多个 model，并用 `default_model` 选择普通 Run 使用的模型。这个
形状与 OpenCode 的 Provider/model catalog、Continue 的多模型条目一致；Cline 和 OpenHands 的最低配置
也都包含 Provider 类型、base URL、API key 和 Model ID。

自动发现不是普通云端 Agent 配置的共同保证。OpenCode 主要对 Ollama、LM Studio 和 vLLM 等已知本地
服务自动发现；普通自定义服务仍要求明确 Model ID。未来的 `models refresh` 只能把 `/models` 当作
候选目录，不能据此宣称 ToolCall、streaming、usage、上下文长度或价格兼容。

参考：[OpenCode Providers](https://opencode.ai/docs/providers/)、
[OpenCode Models](https://opencode.ai/v2/docs/models)、
[Continue config.yaml](https://docs.continue.dev/reference)、
[Cline OpenAI Compatible](https://github.com/cline/cline/blob/main/docs/provider-config/openai-compatible.mdx)、
[OpenHands CLI configuration](https://docs.openhands.dev/openhands/usage/cli/command-reference)。

## “支持 protocol”不等于兼容所有服务

三个 adapter 的离线合同覆盖文本、单个和多个 ToolCall、实际 usage、finish reason、request identity、
timeout、取消、安全错误和禁用 SDK 自动重试。Provider 完成却不返回 usage，或在完成时改变 ToolCall，
BearAgent 会报 `provider_protocol_error`，不会估算或 fallback。

2026-08-23，suite v1.1.1 使用 DeepSeek V4 经 production composition 通过真实 5/5；证据见
[F-0017 P1 live report v1](https://github.com/CherryYang05/BearAgent/blob/main/docs/evidence/F-0017-p1-live-report-v1.json)。
这只证明该次确认配置通过，不代表任意模型服务都兼容。
