# BearAgent 配置参考

本页说明当前已经实现的配置契约。需要可复制的起点时，请使用仓库根目录的
[config.example.json](../../config.example.json)；实际密钥只写入被 Git 忽略的 `data/config.json`。

初学者最容易混淆两个文件：

```text
data/config.json
  回答“连接哪个模型服务”：protocol、base_url、api_key、models

data/p1-run-profile.json
  回答“这次 Agent 怎样运行”：provider_id、instructions、Tool、预算
```

Profile 通过 `provider_id` 引用 config。它不会复制 API key、URL 或模型价格。

## 从最小例子开始

下面只展示字段关系；请从仓库示例复制，不要把占位值直接用于运行：

```json
{
  "schema_version": 1,
  "providers": [
    {
      "provider_id": "my-provider",
      "name": "My model service",
      "protocol": "openai_chat_completions",
      "base_url": "https://example.invalid/v1",
      "api_key": "replace-only-in-local-data-file",
      "models": [{ "model_id": "my-model" }],
      "default_model": "my-model"
    }
  ]
}
```

这不是“自动发现”配置。BearAgent 不根据公司名或 URL 猜协议，也不会在一个协议失败后把同一份
Prompt 和 key 试发给另一个端点。

## config v1

顶层对象和 Provider 条目都拒绝未声明字段。

| 字段 | 类型与限制 | 作用 |
|---|---|---|
| `schema_version` | 固定为整数 `1` | 选择 config v1 契约 |
| `providers` | 1–32 个条目，`provider_id` 唯一 | 声明本机可选择的模型服务 |
| `provider_id` | 符合 Provider ID 格式的字符串 | 供 RunProfile v2 稳定引用 |
| `name` | 1–128 个字符，无首尾空白和控制字符 | 给人看的服务名称 |
| `protocol` | `openai_responses`、`openai_chat_completions` 或 `anthropic_messages` | 显式选择 wire adapter，不探测或 fallback |
| `base_url` | 最长 2048 字符的绝对 HTTPS URL | 禁止账号密码、query、fragment、反斜杠和非法端口 |
| `api_key` | 1–8192 个字符，无空白或控制字符 | 只交给选中的 adapter，使用 `SecretStr` 遮蔽 |
| `models` | 1–128 个条目，`model_id` 唯一 | 声明这个 URL 和 key 下允许使用的模型 |
| `default_model` | 必须等于一个已列出的 `model_id` | 普通 Run 默认使用的模型 |

每个 Model 条目包含必填的 `model_id`，并可包含 1–128 个字符的显示名 `name` 和 `thinking_mode`。
`thinking_mode` 默认为 `provider_default`；当前只有 `openai_chat_completions` 可以显式设为 `disabled`。
显示名不能有首尾空白或控制字符。Config 不接受 `pricing`；普通 Run 使用内部 `unpriced` 价格版本，
真实 gate 的价格快照和费用上限由 gate 参数单独提供。

## 选择和审计行为

[RunProfile v2 示例](../../examples/run-profile-v2.example.json)只保存 `provider_id`，不重复保存 model、
URL、key 或 pricing。Bootstrap 精确查找 Provider，再使用其 `default_model` 和 `protocol` 创建 adapter；
找不到条目或配置非法时，在创建数据库和 Run 前失败。

BearAgent 根据 Provider 的非密钥字段计算 `config_version`。修改名称、protocol、base URL、models、
非默认 thinking mode 或 default model 会得到新版本；只轮换 API key 不会改变审计版本。Event 不保存 base URL、key、
Authorization header 或配置路径。

## 文件和密钥边界

- `config.example.json` 是可提交的占位模板，不得包含真实密钥；
- `data/config.json` 是默认运行时配置，已被 Git 忽略，只应由本机用户编辑；
- 配置必须是有界、UTF-8 的普通文件；link、特殊或超大文件、读取期间替换会被拒绝；
- Objective、模型输出和 Tool 输出不能选择、读取或修改 Provider 配置；
- 不要把真实 key 放进命令行、RunProfile、Event、日志、报告、Artifact、截图或 issue。

旧的 [RunProfile v1 示例](../../examples/run-profile-v1.example.json)仍用于兼容已有配置。新配置应使用
config v1 与 RunProfile v2。

## 配置失败时先看哪里

| 现象 | 先检查 | 为什么在 Run 创建前失败 |
|---|---|---|
| 找不到 Provider | profile 的 `provider_id` 是否与 config 完全一致 | 不允许静默换到另一个 Provider |
| 找不到默认模型 | `default_model` 是否出现在同一条目的 `models` | 不把未知模型名交给 SDK |
| URL 被拒绝 | 是否为绝对 HTTPS URL，是否含 query、fragment 或账号信息 | 避免把凭据和不稳定参数混进 endpoint |
| protocol 被拒绝 | 是否为三种精确枚举之一 | adapter 选择必须可审计 |
| key 看起来正确但仍失败 | 是否有首尾空白、换行或复制进了错误文件 | config 对 secret 仍做有限边界校验 |

更完整的操作和退出码见[命令行手册](../../site/src/content/docs/zh-cn/guides/cli.md)。
