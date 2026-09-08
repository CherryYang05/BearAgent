---
title: 命令行手册：运行、查看与排错
description: 从源码安装 BearAgent，配置模型服务和 Run profile，运行本地文件任务，并用 inspect/events 核对已经保存的事实。
bearStatus: mixed
sourceRefs:
  - F-0020
  - F-0021
  - ADR-0020
  - ADR-0018
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

第一次使用请先读[读一份文档并核对结果](/zh-cn/learn/first-run/)，本文用于查阅参数与排错。

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
和 2026-08-23 的 DeepSeek V4 suite v1.1.1 真实 5/5 分开验证，构成历史 P1 完成证据。F-0020 已合入 main，
P1 已收口。F-0021 工作分支新增只读 replay/check，本地实现不代表已进入 `v0.1.0` 或 main；正式
交付状态以 Spec 为准。进程中断后可以查询已提交事实，但不会自动恢复 Run。P1 也没有 Approval、sandbox、shell、Web UI 或任意网络 Tool。
:::

## 1. 从源码安装

当前仓库尚未声明 PyPI 发布完成，也没有确定公开分发许可证。请先从源码运行：

```console
git clone https://github.com/CherryYang05/BearAgent.git
cd BearAgent
uv python install 3.12
uv sync --all-groups --locked
uv run bearagent doctor
```

`doctor` 退出 0 表示当前 Python 版本受支持。机器读取时使用：

```console
uv run bearagent doctor --json
uv run python -m bearagent doctor --json
```

后文用 `uv run bearagent` 表示源码环境中的命令。安装 wheel 后可以直接写 `bearagent`，命令语义
相同；`python -m bearagent` 也进入同一个 CLI。

### 查看版本、命令和选项

| 命令 | 用途 |
|---|---|
| `bearagent --version` | 打印包版本 |
| `bearagent init` | 创建缺失配置，保留已有文件 |
| `bearagent doctor` | 检查 Python 与本地运行环境 |
| `bearagent doctor --check-config` | 离线检查配置与启动预算 |
| `bearagent run OBJECTIVE` | 执行一个文件任务 |
| `bearagent run inspect RUN_ID` | 查看 Reducer projection 与 Artifact |
| `bearagent run events RUN_ID` | 分页查看已提交 Event |
| `bearagent run replay RUN_ID` | 从 Event 重建状态并对照 projection；F-0021 分支 |
| `bearagent run check` | 分页检查未结束或异常的 Run；F-0021 分支 |

```console
uv run bearagent --help
uv run bearagent doctor --help
uv run bearagent run --help
uv run bearagent run execute --help
uv run bearagent run inspect --help
uv run bearagent run events --help
uv run bearagent run replay --help
uv run bearagent run check --help
```

`run --help` 显示命令组、查询子命令和默认路径。`run execute --help` 列出执行 Run 的全部选项，
不会真正执行任务。正常使用仍写 `run OBJECTIVE`，不用增加 execute。

## 2. 使用默认路径

| 内容 | 默认路径 | 作用 |
|---|---|---|
| workspace | 当前目录 `.` | Tool 可访问的工作资料根目录 |
| config | `data/config.json` | 模型服务、协议、URL、key 与默认模型 |
| profile | `data/p1-run-profile.json` | Agent 说明、Tool 名单与预算 |
| database | `data/bearagent.db` | Event 与查询用的 projection |

路径都相对于启动命令的当前目录。正常运行不需要重复指定；在同一目录执行即可：

```console
uv run bearagent run "阅读 docs/index.md，把简介写到 outputs/intro.md"
```

`--workspace` 只改变工作资料根目录，不改变配置或数据库位置。临时阅读其他资料时可以单独传它：

```console
uv run bearagent run "阅读 README.md，把摘要写到 outputs/summary.md" --workspace ../my-project
```

Artifact 写到指定 workspace 的 `outputs/`，Event 仍进当前目录的默认数据库。只有需要其他配置或记录
时才使用 `--config`、`--profile`、`--database`。后续 inspect/events 要使用同一数据库；不存在时失败，
不会悄悄创建空库。

四个 Tool 分别提供一层目录列表、UTF-8 分行读取、普通字符串搜索与 outputs 原子写入。绝对路径、
`..`、UNC、设备名、symlink、junction、特殊文件和多硬链接文件不可访问。根目录的 `data/`、`.git/`、
`.env`、`.env.*` 与实际 config/profile/数据库及 SQLite sidecar 也受保护。列表标为 blocked，搜索
跳过，直接访问返回 `workspace_path_denied`。普通输入中的敏感文字仍可能发给所配置的模型。

## 3. 初始化一次，然后离线检查

```console
uv run bearagent init
```

命令建立缺失的 config、profile 与 `data/.gitignore`，现有文件不会被覆盖。填写 config 的协议、URL、
key、models 和 default_model，第一次保留 `provider_id: primary`。初始化不会连接模型；空 key 不能运行。

```console
uv run bearagent doctor --check-config
```

检查与真正启动共用本地校验，验证 JSON、Provider 引用、Tool 名单、workspace 和非零预算；不创建
数据库或 Provider client。通过不代表服务在线、key 有效、余额足够或某个目标的 Context 一定能装下。
`--check-config --json` 增加 `configuration_ready` 与安全 message；普通 doctor JSON 保持兼容。
自定义路径检查接受与 run 相同的四个路径选项，但不打开数据库；legacy v1 环境密钥不由此检查。

生成的 profile 限制为 8 次模型、16 次 Tool、80,000 tokens 和 120 秒的新调用调度窗口，模型单次 timeout
为 30 秒。原有示例 profile 仍是零预算演练模板；直接运行只会保存 `budget_exhausted`。旧版本没有 init
时可把 config 示例和 profile 示例手工放到默认路径，再设置非零预算。

普通 v2 Run 为 `unpriced`。费用数值 0 不代表免费，profile 的 `max_cost_microusd` 也不能约束真实账单。
调用次数与 token/time 预算限制新 Activity；已经开始的调用仍需结束并保存，可能使累计用量超过上限。
实际账单限额应在服务方设置。字段说明见[配置一次模型服务](/zh-cn/learn/configure-model-service/)。

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

```console
uv run bearagent run "比较 docs 中的架构和路线图，把结论写到 outputs/report.md"
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

```console
uv run bearagent run -- "inspect"
uv run bearagent run -- "-比较两份文档"
```

CLI 会先把 `Allocated Run ID: ...` 写到 stderr。这只表示已经分配 ID，不表示 `RunCreated` 已经
提交。human 输出随后显示终态、预算 usage、每个 Activity、Artifact 路径/hash、最终文本或安全 Error。

JSON 模式适合脚本：

```console
uv run bearagent run "阅读 docs/index.md，生成 outputs/report.md" --json
```

stdout 恰好是一个对象；进度、预分配 Run ID 和一行一条的结构化运行诊断都在 stderr，不会破坏 JSON
管道。诊断只包含组件、操作、关联 ID、Event type/sequence、有限耗时和错误码，不复制 objective、
模型文本、Tool 参数/结果或原始异常。
version 1 的精确 JSON Schema 快照位于 `tests/contract/snapshots/cli_schemas.json`；脚本应按
`schema_version` 解析，不要依赖 human 文本行。

stderr 不是恢复记录。日志丢失或输出失败不会改变 Run；判断已经发生什么仍使用 `inspect/events`。
完整 Event JSON 可能含敏感业务内容，不能与默认诊断日志混为一谈。

## 6. 查看一个 Run 的当前状态

```console
uv run bearagent run inspect RUN_ID
uv run bearagent run inspect RUN_ID --json
```

把 `RUN_ID` 换成实际 ID。`inspect` 读取 Reducer projection，并从已提交 Tool Event 重建 Artifact 元数据。
它显示：

- Run 状态和最后一个 Event sequence；
- 模型次数、token、micro-USD 与 Tool 次数；
- 每个模型/Tool Activity 的状态；
- terminal Error；
- Provider ID、config version、protocol，以及声明的 Policy/Tool contract fingerprint；
- 已提交的 Artifact 路径、字节数和 SHA-256。

它不会调用模型或 Tool，不会重新执行 Run，也不会从文件系统猜测未提交的 Artifact。Artifact hash
记录的是写入时的内容，查询不会重新读取文件校验。model 与 pricing version 可在 `events --json` 的
RunCreated payload 中查阅。

`succeeded` 只表示模型给出了有效终态回答。请打开产物，独立核对文件与内容是否满足请求。

## 7. 分页查看 Event

```console
uv run bearagent run events RUN_ID --after-sequence 0 --limit 100
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

```console
uv run bearagent run events RUN_ID --after-sequence 100 --limit 100 --json
```

## 8. projection 不可用或进程中断后，先只读检查

以下入口在 F-0021 工作分支可用，P1 的 `v0.1.0` 不包含它们。它们只读取已有数据库，不需要
config、profile 或模型凭据，也不调用模型或 Tool。

```console
uv run bearagent run replay RUN_ID
uv run bearagent run replay RUN_ID --json
uv run bearagent run check --limit 100 --json
```

`replay` 返回 Event 推导的状态、最后 sequence、state hash 和 projection 对照结果。
例如 Event 已记录 `RunSucceeded`，但 projection 行丢失时，仍显示 `succeeded` 和 `missing`，
退出 1 提醒查看；查询不会修复这行。若 Event 本身缺口或格式不受支持，则退出 2，不返回完整状态。

| 对照值 | 表示什么 |
|---|---|
| `matched` | Event 推导的状态与 projection 相同 |
| `missing` | Run projection 或所需 projection 表缺失 |
| `mismatch` | projection 可读，但与重建状态不同 |
| `unreadable` | projection 字段或结构无法读取 |

`check` 从 Event 查找 Run，不依赖 projection 的状态筛选。结果只列出未结束、projection 异常或
读取失败的 Run；`scanned_count` 仍包含健康终态。下一页使用 JSON 中的 `next_after_run_id`：

```console
uv run bearagent run check --after-run-id UUID_FROM_PREVIOUS_PAGE --limit 100 --json
```

以 `has_more` 判断是否还有下一页。`items` 为空也可能需要翻页；UUID 排序不表示执行先后。
每个 Run 是独立的一致快照，各页不是整库的同一时刻；并发新建 Run 可能需要重新扫描。
仍在执行的 Run 也可能显示未结束，不能据此断言崩溃或获准重试。

human 和 JSON 都只输出 ID、状态、sequence、hash、对照值或安全错误码，不导出历史内容。
state hash 用于比较重建状态，不是 Event 签名或执行权限。两条命令沿用 `data/bearagent.db`，
只有查询其他数据库时才传 `--database PATH`；不存在数据库会报错，不会创建空库。

单 Run 输入上限为 10,000 条 Event 和 16 MiB；check 每页默认 100、最多 1,000 个 Run。
每条命令的读取与重建共用 30 秒期限，超过时返回 `query_timeout`。上限内的历史也可能超时：
本地合成样本中，1,000 条约 0.47 秒，10,000 条触发期限。当前没有 Checkpoint；减少 check 页大小
可缩小扫描范围，但不能缩短同一个 Run 的完整重建。

| replay/check 退出码 | 表示什么 |
|---:|---|
| 0 | 所检查范围为健康终态，不代表允许恢复 |
| 1 | 有未结束的 Run 或 projection 异常，需要查看 |
| 2 | 参数、历史、数据库读取或期限失败；有多个结果时取最高严重级别 |

目标恰好是新命令名时，用 `uv run bearagent run -- replay` 或 `uv run bearagent run -- check`。

## 9. 原有命令的退出码和失败排查

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

## 10. 当前限制

- 单用户、单 Agent、单进程；同一 Run 串行执行 Activity；
- 支持 Responses、Chat Completions 和 Anthropic Messages 三种 wire protocol；一次 DeepSeek V4 真实
  5/5 不代表其他服务或协议都已付费联调；
- 只有四个 workspace Tool；没有 shell、代码执行、浏览器、MCP 或任意 HTTP Tool；
- Policy 是启动时固定 allowlist，没有用户 Approval 或持久 Grant；
- SQLite 保存事实，但没有 Checkpoint、resume、retry、Attempt、Receipt 或 `UNKNOWN`；
- check 只报告检查范围与异常项，不是完整 Run 管理列表；没有删除命令、后台 daemon、HTTP API 或 Web UI；
- 任务产生的 `outputs/**` 和数据库由用户管理，P1 不提供生命周期清理。

想理解这些限制背后的理由，继续读[P1 的关键架构取舍](/zh-cn/architecture/p1-decisions/)。要修改 CLI
实现，读[生产 CLI 和查询服务实现导读](/zh-cn/development/run-cli/)。
