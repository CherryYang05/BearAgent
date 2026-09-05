---
title: P1 命令行完整使用手册
description: 从源码安装 BearAgent，配置模型服务和 Run profile，运行本地文件任务，并用 inspect/events 核对已经保存的事实。
bearStatus: implemented
sourceRefs:
  - F-0005
  - F-0017
  - ADR-0014
  - ADR-0015
  - F-0018
  - ADR-0016
  - F-0019
  - ADR-0017
  - cli schema snapshot
---

P1 只有命令行入口。最短使用路径是：准备一个受限 workspace、本机模型 config 和非敏感
RunProfile v2，执行 `bearagent run`，保存屏幕上的 Run ID，再用同一个 SQLite 数据库执行
`inspect` 和 `events`。

```text
objective + config + profile + workspace
        |
        v
bearagent run  ------> outputs/** + SQLite Event
                            |
                            +--> run inspect：看当前状态
                            +--> run events：看有序事实
```

:::caution[当前成熟度]
CLI、SQLite、三种模型协议 adapter、四个 workspace Tool 和 Agent Loop 已经接通。离线 Fake 5/5
和 2026-08-23 的 DeepSeek V4 suite v1.1.1 真实 5/5 分开验证，P1 已关闭。进程中断后可以查询已提交
事实，但不会自动恢复 Run。P1 也没有 Approval、sandbox、shell、Web UI 或任意网络 Tool。
:::

## 1. 从源码安装

当前仓库尚未声明 PyPI 发布完成，也没有确定公开分发许可证。请先从源码运行：

```powershell
git clone https://github.com/CherryYang05/BearAgent.git
cd BearAgent
uv python install 3.12
uv sync --all-groups --locked
uv run bearagent doctor
```

`doctor` 退出 0 表示当前 Python 版本受支持。机器读取时使用：

```powershell
uv run bearagent doctor --json
uv run python -m bearagent doctor --json
```

后文用 `uv run bearagent` 表示源码环境中的命令。安装 wheel 后可以直接写 `bearagent`，命令语义
相同；`python -m bearagent` 也进入同一个 CLI。

### 查看版本、命令和选项

| 命令 | 用途 |
|---|---|
| `bearagent --version` | 打印包版本 |
| `bearagent doctor` | 检查 Python 与本地运行环境 |
| `bearagent run OBJECTIVE` | 执行一个文件任务 |
| `bearagent run inspect RUN_ID` | 查看 Reducer projection 与 Artifact |
| `bearagent run events RUN_ID` | 分页查看已提交 Event |

```powershell
uv run bearagent --help
uv run bearagent doctor --help
uv run bearagent run --help
uv run bearagent run sample-objective --help
uv run bearagent run inspect --help
uv run bearagent run events --help
```

`run --help` 显示 command group 和两个查询子命令。执行 Run 的 `--profile/--workspace/--database/--json`
位于隐藏的 execute handler，因此用任意示例 objective 加 `--help` 查看，不会真正执行任务。

## 2. 准备 workspace、config、profile 和数据库

三个路径各自负责一件事：

| 路径 | 默认值 | 用途 |
|---|---|---|
| workspace | 当前目录 `.` | 四个文件 Tool 能看到的根目录 |
| config | `data/config.json` | Provider、wire protocol、base URL、本机 key 和默认模型 |
| profile | `data/p1-run-profile.json` | Provider 选择、Agent 行为、Tool 名单和预算 |
| database | `data/bearagent.db` | Event 与 Run/Activity projection |

建议第一次使用时显式传入四者，避免从不同目录执行命令后读错配置、workspace 或数据库：

```powershell
uv run bearagent run "阅读 docs 并把总结写到 outputs/summary.md" `
  --config .\data\config.json `
  --profile .\data\p1-run-profile.json `
  --workspace . `
  --database .\data\bearagent.db
```

`run` 会创建数据库父目录并初始化 SQLite。`inspect/events` 只打开已经存在的普通数据库文件；
路径写错时不会悄悄创建空库。

### workspace 当前允许什么

| Tool | 能做什么 | 重要限制 |
|---|---|---|
| `workspace.list` | 列出一层目录 | 有分页和目录项上限 |
| `workspace.read` | 按完整行读取 UTF-8 普通文件 | 有行数、字节和单行长度上限 |
| `workspace.search` | 递归查找普通字符串 | 不是正则表达式；有文件、匹配和时间上限 |
| `workspace.write` | 创建或替换 UTF-8 结果文件 | 目标必须位于 `outputs/**` |

绝对路径、`..`、UNC、设备路径、symlink、junction 和特殊文件会被拒绝。P1 不修改 workspace 中
已有源码或输入文件；`outputs/**` 中已有结果可以通过原子 replace 被完整替换。

## 3. 准备 config v1 和 RunProfile v2

先复制仓库的两个模板：

```powershell
New-Item -ItemType Directory -Force .\data
Copy-Item .\config.example.json .\data\config.json
Copy-Item .\examples\run-profile-v2.example.json .\data\p1-run-profile.json
```

`data/config.json` 已被 Git 忽略。先把占位 `api_key`、`base_url`、wire `protocol`、模型列表和
`default_model` 改成服务的真实配置。`protocol` 只能显式选择 `openai_responses`、
`openai_chat_completions` 或 `anthropic_messages`；BearAgent 不根据厂商、URL 或 model 猜测，也不会
失败后切换 endpoint。

RunProfile v2 使用 `provider_id` 精确选择 config 条目，不重复保存 model、URL、key 或 pricing。模板把
五类预算全部设为 0；直接运行只会保存一个 `budget_exhausted` Run，不会创建 Provider client，也不会
调用模型或 Tool。这适合先验证数据库与查询命令。

真正调用模型前，需要审查并修改：

- `provider_id`：必须命中 config 中唯一条目；
- `instructions` 与三个版本字段：这次 Agent 配置的可追踪身份；
- `max_output_tokens`、`model_timeout_ms`、Context 和 Tool result 上限；
- `tool_names`：必须是排序且不重复的可信 Tool 子集；
- `budget_limits`：模型次数、token、micro-USD、总时间和 Tool 次数上限。

:::caution[普通 Run 不按 catalog 自动计价]
Config v1 明确拒绝 `pricing`，普通 Run 的内部价格版本是 `unpriced`。真实 P1 gate 使用独立、版本化的
pricing snapshot 和总费用上限；日常 CLI 的 `max_cost_microusd` 不能替代 Provider 账单限额。
:::

Profile 必须是最多 128 KiB 的普通 UTF-8 JSON 文件，拒绝未知字段和链接。它不允许保存 API key、
base URL、workspace 绝对路径或数据库路径。

## 4. 理解密钥和旧版 profile 边界

BearAgent 故意不提供 `--api-key`。新配置把 key 只写在被 Git 忽略的本机 `data/config.json` 中；不要把
凭据写进 RunProfile、objective、命令参数、Event、Git、截图或 issue。Config loader 使用 `SecretStr`
遮蔽 key。新 Run 的 Event v4 保存 `provider_id`、非密钥 `config_version`、protocol、model、pricing
version 与声明的 Policy/Tool contract fingerprint，不保存 endpoint、key 或完整 Policy 配置。

Config v1 缺少、空白或非法 key 时，会在数据库和 Run 创建前返回 `invalid_input`。旧 RunProfile v1 仍
为兼容已有配置保留：它只支持 legacy OpenAI Responses 路径，并继续读取 `OPENAI_API_KEY` 与可选的
`OPENAI_BASE_URL`；缺少凭据时，已经建立的 Run 会以安全的 `provider_authentication` 失败。

完整字段和校验规则见[配置参考](https://github.com/CherryYang05/BearAgent/blob/main/docs/reference/configuration.md)。

## 5. 运行一个 Run

```powershell
uv run bearagent run "比较 docs 中的架构和路线图，把结论写到 outputs/report.md" `
  --config .\data\config.json `
  --profile .\data\p1-run-profile.json `
  --workspace . `
  --database .\data\bearagent.db
```

可用选项：

| 选项 | 含义 |
|---|---|
| `--profile PATH` | version 1 或 2 Run profile |
| `--config PATH` | version 1 BearAgent config；RunProfile v2 必需 |
| `--workspace PATH` | Tool 可访问的 workspace 根 |
| `--database PATH` | SQLite EventStore |
| `--json` | stdout 只输出一个 version 1 JSON 对象 |

选项可以放在 objective 前后。如果 objective 恰好是 `inspect`、`events` 或以 `-` 开头，使用
`--` 终止 CLI 解析：

```powershell
uv run bearagent run -- "inspect"
uv run bearagent run -- "-比较两份文档"
```

CLI 会先把 `Allocated Run ID: ...` 写到 stderr。这只表示已经分配 ID，不表示 `RunCreated` 已经
提交。human 输出随后显示终态、预算 usage、每个 Activity、Artifact 路径/hash、最终文本或安全 Error。

JSON 模式适合脚本：

```powershell
uv run bearagent run "生成 outputs/report.md" --json `
  --config .\data\config.json `
  --profile .\data\p1-run-profile.json `
  --workspace . `
  --database .\data\bearagent.db
```

stdout 恰好是一个对象；进度、预分配 Run ID 和一行一条的结构化运行诊断都在 stderr，不会破坏 JSON
管道。诊断只包含组件、操作、关联 ID、Event type/sequence、有限耗时和错误码，不复制 objective、
模型文本、Tool 参数/结果或原始异常。
version 1 的精确 JSON Schema 快照位于 `tests/contract/snapshots/cli_schemas.json`；脚本应按
`schema_version` 解析，不要依赖 human 文本行。

stderr 不是恢复记录。日志丢失或输出失败不会改变 Run；判断已经发生什么仍使用 `inspect/events`。
完整 Event JSON 可能含敏感业务内容，不能与默认诊断日志混为一谈。

## 6. 查看一个 Run 的当前状态

```powershell
uv run bearagent run inspect <run-id> --database .\data\bearagent.db
uv run bearagent run inspect <run-id> --database .\data\bearagent.db --json
```

`inspect` 读取 Reducer projection，并从已提交 Tool Event 重建 Artifact 元数据。它显示：

- Run 状态和最后一个 Event sequence；
- 模型次数、token、micro-USD 与 Tool 次数；
- 每个模型/Tool Activity 的状态；
- terminal Error；
- Provider ID、config version、protocol、model 和 pricing version；
- 已提交的 Artifact 路径、字节数和 SHA-256。

它不会调用模型或 Tool，不会重新执行 Run，也不会从文件系统猜测未提交的 Artifact。

## 7. 分页查看 Event

```powershell
uv run bearagent run events <run-id> `
  --database .\data\bearagent.db `
  --after-sequence 0 `
  --limit 100
```

| 选项 | 范围与语义 |
|---|---|
| `--after-sequence N` | 返回 sequence 大于 N 的 Event；默认 0 |
| `--limit N` | 1 到 10,000；默认 1,000 |
| `--database PATH` | 必须是已有 SQLite EventStore |
| `--json` | 返回完整 version 1 Event page |

human 输出只显示 sequence、时间、Event 类型和 schema version。JSON 会返回完整 payload，其中可能
含用户 objective、模型文本、Tool 参数和 ToolResult。它是显式本地事实导出，不应作为无敏感内容的
普通日志公开。

下一页请求使用上一页 JSON 中的 `next_after_sequence`：

```powershell
uv run bearagent run events <run-id> --after-sequence 100 --limit 100 --json `
  --database .\data\bearagent.db
```

## 8. 退出码和失败排查

| 退出码 | 表示什么 |
|---:|---|
| 0 | 命令成功；`run` 已到 `succeeded` |
| 1 | Run 以 `failed` 终止，或输入、Provider、SQLite、查询/渲染出现安全失败 |
| 2 | Typer 命令语法错误 |

| 现象 | 怎样判断 |
|---|---|
| `budget_exhausted` | profile 的某项预算不允许下一次 Activity；用 inspect/events 查看已提交事实 |
| `provider_authentication` | legacy v1 缺少环境凭据，或 Provider 拒绝认证；检查选中的配置，不要公开 key |
| `invalid_input` | objective、config/profile、Run ID、分页或路径形状无效；v2 配置错误发生在数据库创建前 |
| Tool 路径错误 | Tool failure 会被保存并交回模型；预算允许时模型可以改用合法相对路径 |
| inspect/events 找不到数据库 | 检查 `--database` 是否与 run 完全相同；查询命令不会创建空库 |
| Run 长期显示 `running` | 进程可能在 Activity 边界中断；P1 只如实显示，不会自动 resume 或补写成功 |
| 文件存在但 inspect 没有 Artifact | 写入可能完成，但 Tool completed Event 未提交；P1 不从文件系统反推事实 |

## 9. 当前限制

- 单用户、单 Agent、单进程；同一 Run 串行执行 Activity；
- 支持 Responses、Chat Completions 和 Anthropic Messages 三种 wire protocol；一次 DeepSeek V4 真实
  5/5 不代表其他服务或协议都已付费联调；
- 只有四个 workspace Tool；没有 shell、代码执行、浏览器、MCP 或任意 HTTP Tool；
- Policy 是启动时固定 allowlist，没有用户 Approval 或持久 Grant；
- SQLite 保存事实，但没有 Checkpoint、resume、retry、Attempt、Receipt 或 `UNKNOWN`；
- 没有 Run 列表、删除、导出命令、后台 daemon、HTTP API 或 Web UI；
- 任务产生的 `outputs/**` 和数据库由用户管理，P1 不提供生命周期清理。

想理解这些限制背后的理由，继续读[P1 的关键架构取舍](/zh-cn/architecture/p1-decisions/)。要修改 CLI
实现，读[生产 CLI 和查询服务实现导读](/zh-cn/development/run-cli/)。
