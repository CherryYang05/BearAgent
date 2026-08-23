# BearAgent 配置参考

本页说明当前已经实现的配置契约。需要可复制的起点时，请使用仓库根目录的
[config.example.json](../../config.example.json)；实际密钥只写入被 Git 忽略的 `data/config.json`。

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
