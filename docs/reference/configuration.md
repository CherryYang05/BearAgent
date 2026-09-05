# BearAgent 配置参考

先在准备运行的目录执行以下命令，再编辑 `data/config.json` 的服务信息：

```console
bearagent init
bearagent doctor --check-config
```

`init` 建立缺失的 config、profile 和 `data/.gitignore`，保留已有文件。生成的 key 为空，需要用户填写；
初始化和离线检查不调用模型，也不创建数据库。第一次保留双方的 `provider_id: primary` 即可。
旧版本也可手动复制 [config 模板](../../config.example.json) 和
[零预算 profile](../../examples/run-profile-v2.example.json)，分别放到默认位置。

初学者最容易混淆两个文件：

```text
data/config.json
  回答“连接哪个模型服务”：protocol、base_url、api_key、models

data/p1-run-profile.json
  回答“这次 Agent 怎样运行”：provider_id、instructions、Tool、预算
```

Profile 通过 `provider_id` 引用 config。它不会复制 API key、URL 或模型价格。

这两个文件以及数据库相对于**执行命令时的当前目录**查找。`--workspace` 只改变 Tool 的工作根目录，
不会把 config/profile/database 一起搬过去；日常使用保持在同一目录即可，只有切换资料或运行配置时才
显式覆盖路径。

## 初始化后的运行上限

生成的 profile 允许最多 8 次模型调用、16 次 Tool、80,000 tokens，单次输出最多 1,024 tokens。
总时间达到 120 秒后不再启动新 Activity，模型单次 timeout 为 30 秒。已经开始的调用仍需结束并记账；
token 上限也可能被最后一次调用超过。这些是调度与记账规则，不是服务商账单的精确截断。

`max_cost_microusd` 初值为 1,000,000，保留现有预算 schema 所需的有限字段。普通 v2 Run 为 `unpriced`，
该字段**不能提供一美元账单上限**；`cost_microusd=0` 表示没有按价格计费，不代表免费。实际消费限额
应在 Provider 侧设置。已有零预算不会被初始化改写；离线检查会提示它不能启动正常文件任务。

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
- `data/config.json` 是默认运行时配置，只应由本机用户编辑；init 创建的数据目录忽略规则不改变已跟踪文件；
- 配置必须是有界、UTF-8 的普通文件；link、特殊或超大文件、读取期间替换会被拒绝；
- Objective、模型输出和 Tool 输出不能选择、读取或修改 Provider 配置；
- 根目录 `data/`、`.git/`、`.env`、`.env.*` 对文件 Tool 不可访问；实际 config、profile、数据库及
  SQLite `-wal`、`-shm`、`-journal` 路径也由 bootstrap 保护，包括自定义位置；
- 列目录将受保护条目标为 blocked，搜索跳过；直接访问返回 `workspace_path_denied`。多个硬链接的
  普通文件同样被拒绝，不能通过别名读取配置。这不是任意敏感内容识别或 P3 sandbox；
- 不要把真实 key 放进命令行、RunProfile、Event、日志、报告、Artifact、截图或 issue。

旧的 [RunProfile v1 示例](../../examples/run-profile-v1.example.json)仍用于兼容已有配置。新配置应使用
config v1 与 RunProfile v2。

## 配置失败时先看哪里

`doctor --check-config` 与真正启动共用 `validate_run_configuration`。它检查本地 JSON、引用、Tool
名单、workspace 和非零预算，不初始化 SQLite，不验证网络、API key 有效性、模型兼容性或账单余额。
普通 `doctor` 仍只检查 Python 环境；legacy v1 的环境凭据也不会由此检查。

| 现象 | 先检查 | 为什么在 Run 创建前失败 |
|---|---|---|
| 找不到 Provider | profile 的 `provider_id` 是否与 config 完全一致 | 不允许静默换到另一个 Provider |
| 找不到默认模型 | `default_model` 是否出现在同一条目的 `models` | 不把未知模型名交给 SDK |
| URL 被拒绝 | 是否为绝对 HTTPS URL，是否含 query、fragment 或账号信息 | 避免把凭据和不稳定参数混进 endpoint |
| protocol 被拒绝 | 是否为三种精确枚举之一 | adapter 选择必须可审计 |
| key 看起来正确但仍失败 | 是否有首尾空白、换行或复制进了错误文件 | config 对 secret 仍做有限边界校验 |

更完整的操作和退出码见[命令行手册](../../site/src/content/docs/zh-cn/guides/cli.md)。
