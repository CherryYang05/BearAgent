---
title: 配置一次模型服务，运行不同目标
description: 在 config.json 填写厂商、URL、API key、模型列表和默认模型。
bearStatus: mixed
sourceRefs:
  - F-0032
  - ADR-0018
  - F-0017
  - ADR-0015
  - F-0005
  - F-0018
---

你不需要为每个问题生成一份 Provider JSON。下面两次运行复用同一份 `config.json` 和 RunProfile；
变化的只有 objective：

```console
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

执行 `uv run bearagent init`，打开生成的 `data/config.json` 并填写服务值。旧版本也可手工复制
[config 示例](https://github.com/CherryYang05/BearAgent/blob/main/config.example.json)。下面是服务配置示意；
首次使用可保留生成配置中的 `provider_id: primary`，减少两个文件之间的修改：

```json
{
  "schema_version": 1,
  "providers": [
    {
      "provider_id": "primary",
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

`init` 已生成 `data/p1-run-profile.json`，小任务可以先使用其中的有限默认预算。各部分的作用是：

- 顶层 `provider_id` 必须与 config 中的条目一致；
- `agent_config` 只保存 Agent 指令、Context/Prompt 版本、Tool 白名单和调用限制；
- `budget_limits` 决定最多运行多少次、使用多少 token、调用多少 Tool；费用字段只约束有定价的本地账面估算，不代表真实账单限额。

RunProfile v2 不接受 `agent_config.model` 或 `agent_config.pricing`。Bootstrap 会从 Provider 的
`default_model` 构造 `unpriced` 的内部 `AgentConfig`。公开示例故意把预算设为 0，因此只会留下可检查的
`budget_exhausted`，不会调用模型。`init` 生成的本机 profile 则使用有限非零预算；普通 Run 不计算真实费用。

## 第三步：运行并检查

先执行 `uv run bearagent doctor --check-config`。这项检查不联网，也不创建数据库；通过后再运行目标。

CLI 默认读取 `data/config.json` 和 `data/p1-run-profile.json`，因此正常运行不需要重复传路径：

```console
uv run bearagent run "阅读 docs，并把总结写到 outputs/summary.md"

uv run bearagent run inspect RUN_ID --json
uv run bearagent run events RUN_ID --json
```

把 `RUN_ID` 换成实际值。只有临时使用其他配置时，才需要用 `--config` 或 `--profile` 覆盖默认路径。

缺少、空白或非法 key 时，config 会在创建数据库和 Run 前失败。新 Run 使用 Event schema v4 保存
`provider_id`、自动计算的 `config_version`、`protocol` 与可信 contract fingerprint，不会保存 base
URL、key 或 HTTP header。F-0017 引入的 Event v3 继续可读。
用户不需要手工填写 `config_version`；非密钥 Provider/model 字段变化时，它会自动变化。

Version 1 profile 仍可读取，并映射到 legacy `openai_responses` 与 `OPENAI_API_KEY`。这是已有配置的
兼容路径；新的 v2 config 使用直接填写的 `api_key`。

## 配置不会成为工作资料

文件访问 Boundary 在打开内容之前保护 `data/` 与实际自定义 config、profile、数据库及 sidecar，
read 和递归 search 都受同一规则约束。SecretStr 另负责遮蔽配置对象；仅有对象遮蔽，不能防止原始
文件被其他路径读出。普通输入文件里的敏感内容仍可能发给模型，这不是任意秘密识别器。

五任务 live gate 是研发验收流程，需要单独确认价格、模型与费用，不是普通用户的配置步骤。
协议和测试入口见[模型 Provider adapter](/zh-cn/development/model-provider/)。

## “支持 protocol”不等于兼容所有服务

三个 adapter 的离线合同覆盖文本、单个和多个 ToolCall、实际 usage、finish reason、request identity、
timeout、取消、安全错误和禁用 SDK 自动重试。Provider 完成却不返回 usage，或在完成时改变 ToolCall，
BearAgent 会报 `provider_protocol_error`，不会估算或 fallback。

2026-08-23，suite v1.1.1 使用 DeepSeek V4 经 production composition 通过真实 5/5；证据见
[F-0017 P1 live report v1](https://github.com/CherryYang05/BearAgent/blob/main/docs/evidence/F-0017-p1-live-report-v1.json)。
这只证明该次确认配置通过，不代表任意模型服务都兼容。
