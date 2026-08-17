---
title: "Feature: Bounded read-only workspace tools"
status: implemented
spec_id: F-0007
milestone: P1
owner: CherryYang05
created: 2026-08-16
last_updated: 2026-08-16
implemented_in: "codex/F-0007-workspace-read-tools"
related_adrs:
  - ADR-0004
  - ADR-0005
  - ADR-0007
  - ADR-0011
---

# F-0007：把 workspace 中的目录和文本安全地交给 Agent 阅读

## 1. 为什么现在要做

用户希望 BearAgent 阅读 `docs/architecture/overview.md` 时，模型现在只能提出一个
`workspace.read` 请求。F-0006 已经能检查 Tool 名称、参数、权限、timeout 和结果大小，但仓库里还
没有真正打开文件的 Tool。

直接把模型给出的字符串交给 `Path.open()` 会留下几个不同问题：`../` 或绝对路径可能离开
workspace，Windows 盘符和设备名可能绕开普通文件语义，symlink 或 junction 可能把一个看似在
workspace 内的路径指向外部，超大目录和文件也可能占满时间或上下文。

F-0007 只建立只读边界。完成后，开发者可以把一个明确的 workspace 根目录交给三个 Tool，再通过
F-0006 的统一 Executor 列目录、分段读 UTF-8 文本和搜索普通字符串。完整 Agent Loop 和 CLI 仍要
等 F-0016、F-0005。

## 2. 本次交付

- 一个固定的 workspace 边界：启动时接收一次根目录，之后只处理规范化的相对路径；
- `workspace.list`：列出一层目录内容，结果稳定排序并支持有界分页；
- `workspace.read`：按行读取一段 UTF-8 普通文件，并明确告诉调用者后面是否还有内容；
- `workspace.search`：在一个子目录中递归查找普通字符串，返回有界、稳定排序的匹配行；
- 统一的安全失败：路径越界、链接跳转、类型不符、文件不存在、非文本内容和资源超限都返回有限的
  `ToolResult`，不暴露 workspace 的绝对路径；
- Windows 和 POSIX 安全测试，以及三个真实 Tool 经过 F-0006 Executor 的集成测试。

## 3. 本次不做

- 不写文件。`outputs/**` 原子写和 Artifact 属于 F-0008；
- 不接模型、Agent Loop、EventStore 或 CLI；
- 不读取二进制文件、压缩包、图片、PDF 或未知编码；
- 不实现正则表达式、glob、`.gitignore` 解释、全文索引或外部 `rg` 进程；
- 不自动重试，不增加 Attempt、Checkpoint、Receipt 或 `UNKNOWN`；
- 不把整个 workspace 当成可信内容。读到的文字仍然不能授予权限；
- 不承诺抵御一个能够持续、并发改写整个 workspace 目录树的本机攻击者。F-0007 会拒绝静态链接跳转，
  并检测“检查后、打开前”目标文件被替换；更强的目录句柄约束和隔离挂载属于 P3。

## 4. 需要先说明的约定

假设启动代码把 `D:\BearAgent` 指定为 workspace 根目录。模型只会看到下面这种路径：

```json
{"path": "docs/architecture/overview.md"}
```

这里的 `path` 是 **workspace 相对路径**。输入可以使用 `/` 或 `\`；`prepare` 会在权限检查前统一
整理成使用 `/` 的形式，`.` 单独表示根目录。它不是操作系统绝对路径，也不会在结果或错误中变回
`D:\BearAgent\...`。

路径检查分两次发生：

```text
模型给出相对路径
  -> Tool.prepare 只检查写法并整理成唯一形式
  -> F-0006 Policy 判断这个规范化请求是否允许
  -> workspace adapter 检查真实文件类型和边界
  -> 读取有限内容并返回 ToolResult
```

第一次检查不能访问文件系统，因为 F-0006 已规定 `prepare` 必须是纯检查。第二次检查只能留在具体
adapter 中；Runtime 不应知道 Windows junction、文件编码或目录遍历细节。

## 5. 使用场景

### 先看一个目录里有什么

调用者请求 `workspace.list({"path": "docs", "offset": 0, "limit": 100})`。Tool 只列出 `docs`
的直接子项，按规范化相对路径排序。结果达到本次条数上限时返回 `next_offset`，调用者可以继续读取，
不需要一次拿走整个目录。

### 分段阅读一份文档

调用者请求 `workspace.read({"path": "README.md", "start_line": 1, "max_lines": 200})`。成功结果包含
实际返回的起止行、文本和 `next_start_line`。文本超过单次输出上限时，Tool 停在完整行边界并告诉
调用者下一次从哪里继续，不返回半个 UTF-8 字符或伪装成完整文件。

### 在 docs 中查找一个普通字符串

调用者请求 `workspace.search({"path": "docs", "query": "UNKNOWN", "case_sensitive": true})`。
Tool 不解释正则表达式，只在普通 UTF-8 文件中搜索字面字符串。匹配按路径、行号排序；达到文件数、
总读取字节数、匹配数或时间上限时，结果用 `truncated` 和 `limit_reason` 说明为什么停下。

### 模型尝试离开 workspace

`../secret.txt`、`C:/Users/name/.env`、`\\server\share\file`、`docs/link-out/secret.txt` 和 Windows
设备名都被拒绝。Tool 不尝试“修正”为某个可访问路径，也不在错误中返回真实目标。

## 6. 必须满足的行为

### 6.1 相对路径只有一种可执行含义

- workspace 根目录必须已经存在、是目录，且自身不是 symlink 或 junction；构造时保存规范化根路径；
- 模型路径可以使用 `/` 或 `\`；两者都先变成 `/`。拒绝绝对路径、盘符、UNC、以单个分隔符开头的
  rooted path、NUL、控制字符、`..`、冒号、末尾空格或点，以及 Windows 保留设备名；
- 规范化路径按 `/` 拆成段，再由当前平台的 `Path` 连接到 workspace 根目录。Windows 和 Unix 因而
  使用各自文件系统 API，但 Policy 始终检查同一种路径文本；Unix 中名称本身含 `\` 的文件不开放；
- 重复的 `/` 和中间的 `.` 会被整理，根目录只表示为 `.`；规范化结果写回 `PreparedToolRequest`；
- `prepare` 不调用 `exists()`、`resolve()`、`stat()` 或其他 I/O；
- 执行时逐段检查真实路径。任何 symlink、junction 或可作为名称跳转的 reparse point 都不跟随；
- 真实目标必须仍在启动时固定的根目录下，而且只接受普通文件或目录；
- 打开普通文件前后比较文件身份。目标在检查和打开之间被替换时，关闭句柄并返回拒绝，不读取新目标；
- 直接请求被阻止的链接会失败。目录列出和递归搜索可以报告其名称，但永远不读取目标，也不暴露链接
  指向哪里。

### 6.2 三个 Tool 保持小而明确

| Tool | 输入重点 | 成功结果重点 |
|---|---|---|
| `workspace.list` | `path`、`offset`、`limit` | 直接子项、类型、下一页位置 |
| `workspace.read` | `path`、`start_line`、`max_lines` | UTF-8 文本、实际行范围、下一段起点 |
| `workspace.search` | `path`、`query`、`case_sensitive`、`max_results` | 匹配路径、行号、有限行文本、截断原因 |

- 三个 Tool 都声明 `READ_ONLY`，使用有限 timeout、输入上限和输出上限；
- 参数中的 `limit`、`max_lines` 和 `max_results` 只能缩小可信上限，不能扩大 Tool 注册时的限制；
- 目录项和搜索结果按规范化相对路径排序；同一文件中的匹配按行号排序；
- `workspace.list` 只列一层。递归读取只能通过 `workspace.search` 的有界遍历发生；
- `workspace.read` 只接受普通 UTF-8 文件；遇到非法 UTF-8、NUL 字节或超出文件读取上限时整体失败；
- `workspace.search` 跳过链接、特殊文件和非 UTF-8 文件，并返回有限的跳过计数；它不返回绝对路径、
  链接目标或原始操作系统异常；
- 每个结果都保留原 `ToolCallId`，失败形状继续遵守 F-0006 `ToolResult` 契约。

### 6.3 资源限制来自可信 Tool 配置

每个 Tool 需要固定下面这些硬上限：单次目录条数、单个可读文件字节数、单次返回行数、单行字符数、
搜索文件数、搜索总字节数、匹配数、结果 JSON 大小和执行时间。具体常量在实现时集中放在 workspace
adapter 内，不散落到 Runtime 或测试中。

首个实现使用下面的可信上限：

| 范围 | 上限 |
|---|---|
| 路径 | 1,024 UTF-8 bytes、64 段、每段 255 bytes |
| 目录 | 最多检查 5,000 项；单页最多返回 200 项，默认 100 项 |
| 文本 | 单文件 4 MiB、单行 64 KiB；单页最多 500 行，默认 200 行、文本 256 KiB |
| 搜索 | 深度 32、文件 2,000、总读取 16 MiB、匹配 100、单行预览 2,048 字符 |
| ToolResult | JSON 最多 512 KiB |
| timeout | list 3 秒、read 5 秒、search 10 秒 |

达到“结果数量”类上限可以返回成功但必须标记 `truncated`；无法安全读取一个请求目标时返回失败。
调用者不能只根据结果数组是否非空来猜测内容是否完整。

### 6.4 失败代码可供后续 Event 使用

F-0007 在公共 `ErrorCode` 中增加下面几类稳定错误；它们都属于 `TOOL`：

| 发生了什么 | 代码 |
|---|---|
| 真实路径会经过链接、离开边界，或打开前后对象不一致 | `workspace_path_denied` |
| 路径不存在 | `workspace_not_found` |
| 请求目录却得到文件，或请求文件却得到目录/特殊对象 | `workspace_wrong_type` |
| 文件不是支持的 UTF-8 文本 | `workspace_not_text` |
| 文件、遍历或单行内容超过可信上限 | `workspace_limit_exceeded` |
| 操作系统拒绝读取或读取期间发生其他安全失败 | `workspace_access_failed` |

参数字段缺失、类型错误或相对路径写法非法，仍使用 F-0006 的 `tool_invalid_input`；Executor 的总体
timeout 仍使用 `tool_timeout`。所有可见消息和 details 都有限，不包含绝对路径、链接目标、堆栈或
原始异常。

## 7. 对外入口和模块连接

| 位置 | 负责什么 |
|---|---|
| `domain.errors` | 增加可序列化的 workspace 错误代码 |
| `adapters.tools.workspace_boundary` | 规范化相对路径，固定根目录，执行真实文件边界检查 |
| `adapters.tools.workspace_list` | 实现一层目录列出 |
| `adapters.tools.workspace_read` | 实现分段 UTF-8 读取 |
| `adapters.tools.workspace_search` | 实现有界普通字符串搜索 |
| `adapters.tools` | 导出三个 Tool 和一个按根目录构造它们的轻量工厂 |

这些 adapter 只实现已有 `ports.tools.Tool`。它们不会被 `domain`、`runtime` 或 `ports` 导入。
F-0016 以后负责把工厂返回的 Tool 放进 `ToolRegistry`，再由现有 `ToolExecutor` 调用。

本 Feature 不增加 CLI/API，不修改 `bootstrap.py` 的运行入口，也不让调用者绕过 Executor 直接向模型
暴露 adapter。

## 8. 状态和保存的数据

F-0007 不保存状态，不增加 Event、SQLite 表或 migration。目录项、文本和搜索匹配只存在于本次
`ToolResult` 中。

F-0016 接入 Agent Loop 后，才把规范化请求和有限结果写成 Tool Activity Event。workspace 的绝对
根目录不应进入模型上下文或公开 Event；需要诊断时只记录由启动配置生成的非敏感 workspace 标识。

## 9. 失败时会发生什么

- 参数或路径写法错误发生在 `prepare`，因此 Policy 和文件访问都不会运行；
- 真实路径不存在、类型不符或经过链接时，Tool 返回一个失败结果，不尝试相近路径；
- 读取到非法文本或资源上限时，不把半截文件伪装成成功；只有明确支持分页或截断的 list/read/search
  结果才能以 `truncated` 成功返回；
- Executor timeout 或调用者取消时不自动重试。文件 Tool 是只读的，因此不会留下待核对的外部写入；
- 使用工作线程避免同步磁盘读取阻塞 Runtime 事件循环。取消等待不等于操作系统能立即终止已经开始的
  单次读取，所以 adapter 自身仍要按块检查 deadline 和字节上限；
- 进程中断后没有恢复动作。是否发起下一次读取，由后续 Agent Loop 或其他调用方决定；
- F-0007 不产生部分写入，也不会进入 `UNKNOWN`。

## 10. 安全与隐私

- 模型、Prompt、Skill、workspace 文件内容和 ToolResult 都不能修改 workspace 根目录或允许名单；
- 所有真实读取都经过 F-0006 Registry、`prepare`、固定 Policy 和 Executor；
- workspace 根目录由可信启动代码注入，绝不从单次 Tool 参数读取；
- 不跟随 symlink、junction 或目录遍历中的链接，不打开 socket、FIFO、设备或其他特殊对象；
- Windows 盘符、UNC、NTFS alternate data stream 写法和保留设备名在纯路径检查时就被拒绝；
- 结果不包含绝对路径、链接目标、权限位、所有者、原始异常或环境变量；
- 搜索内容仍是不可信文字。Prompt injection 只能成为 ToolResult 内容，不能改变 Policy；
- F-0007 的边界适用于 P1 单用户、单进程的受控本地 workspace。面对能够并发替换任意祖先目录的本机
  攻击者时，不宣称等同 sandbox；P3 必须用隔离挂载和独立 runner 重新建立更强边界。

## 11. 怎样检查执行过程

当前调用者从 `ToolResult` 可以看到：规范化相对路径、返回范围、是否截断、截断原因、有限跳过计数，
或一个稳定安全错误。它看不到宿主绝对路径和原始操作系统错误。

F-0007 不写 Event。F-0016 接入后，Tool 名称、规范化参数、结果范围、截断原因和稳定 ErrorCode 必须
进入 Tool Activity Event；文件全文不应额外复制进日志。

## 12. 上线与回退

没有数据库迁移或默认 CLI 行为变化。F-0007 只新增可显式构造的 Tool adapter；在 F-0016 注册它们
之前，现有用户入口不会访问 workspace。

回退时删除三个 Tool、workspace 边界辅助代码和新增错误码即可。没有持久数据需要转换。若未来 Event
已经保存这些错误码，回退版本仍须把未知历史数据视为显式不兼容，不能悄悄改写。

## 13. 验收标准

1. `workspace.list` 能稳定分页列出普通目录；`workspace.read` 能按完整行分段读取 UTF-8 文件；
   `workspace.search` 能稳定返回普通字符串匹配；
2. 三个 Tool 使用同一个 workspace 边界组件，但彼此不导入具体实现，也不把文件系统类型带进 Runtime；
3. 使用 `/` 和 `\` 的同一相对路径会得到相同规范化结果；绝对路径、盘符、UNC、rooted path、`..`、
   设备名、alternate data stream、symlink、junction 和特殊文件都在访问外部内容前被拒绝；
4. 测试在目标文件于检查后被替换时得到拒绝，且没有读取替换后的内容；
5. 目录、文件、行、搜索和 JSON 结果的硬上限不能被模型参数扩大；分页或截断结果明确说明不完整；
6. 失败结果能区分路径拒绝、不存在、类型不符、非文本、资源超限和访问失败，并且不泄露绝对路径、
   链接目标、原始异常或秘密；
7. 三个真实 Tool 经过 `ToolRegistry + FixedToolPolicy + ToolExecutor` 的集成测试，参数/Policy 失败时不
   访问文件，timeout 和取消不触发自动重试；
8. 不增加生产依赖、Event、SQLite migration、shell 或网络调用；公共 Schema、架构边界、完整测试、
   工程文档和站点构建全部通过。

## 14. 验证方式

- Unit：路径规范化、参数模型、分页、UTF-8 分段、普通字符串匹配和限制常量；
- Contract：三个 adapter 都满足现有 `Tool` prepare/execute 契约，公共 ErrorCode Schema 更新；
- Integration：临时 workspace 中通过 Registry、固定 Policy 和 Executor 运行三个 Tool；
- Recovery：取消和 timeout 不重试，只读 Tool 不留下外部写入；不测试 P2 重启恢复；
- Security：Windows/POSIX 路径变体、symlink、junction（平台支持时）、特殊文件、最终文件替换、超大
  文件/目录/行、异常脱敏和 Prompt 内容提权；
- Eval/manual：不接模型效果评测；用一个固定小 workspace 手工核对列出、分段读取和搜索结果。

## 15. 文档同步

- [x] 更新工程 `docs/` 中的 Spec、Plan、ADR、架构和 Roadmap；
- [x] 在站点学习路径新增一页，从“模型想读 README”解释相对路径、分页和文本限制；
- [x] 在站点开发者文档新增 workspace Tool 入口、边界组件和重点安全测试；
- [x] 更新站点当前状态，明确“已有只读 Tool，但还没有写入、Agent Loop 或 CLI Run”；
- [x] 确认部署文档无需变化；
- [x] 更新公共 ErrorCode Schema 快照。

## 16. 已解决的问题

项目所有者于 2026-08-16 接受本 Spec：只提供 list/read/search，文本固定为 UTF-8，搜索固定为普通
字符串；所有 symlink、junction 和名称跳转都拒绝；F-0007 不宣称抵御能并发改写任意祖先目录的本机
攻击者。项目所有者同时要求兼容 Windows 和 Unix 路径输入，因此 `/` 与 `\` 都可作为输入分隔符，
但必须在 Policy 前统一规范化成 `/`。
