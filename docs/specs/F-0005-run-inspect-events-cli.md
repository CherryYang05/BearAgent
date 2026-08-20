---
title: "Feature: Production Run, inspect, and Event CLI"
status: implemented
spec_id: F-0005
milestone: P1
owner: CherryYang05
created: 2026-08-20
last_updated: 2026-08-20
implemented_in: "codex/F-0005-cli-run-inspect-events"
related_adrs: [ADR-0003, ADR-0004, ADR-0009, ADR-0010, ADR-0013, ADR-0014]
---

# F-0005：从命令行运行文件任务，并查看同一批已保存事实

## 1. 为什么现在要做

用户已经可以在 Python 测试中让 `AgentLoop` 调用真实 workspace Tool，并把每次模型和 Tool Activity
保存到内存或 SQLite Store。可是当前命令行只有 `doctor`。用户还不能组装真实 Provider、SQLite、
workspace 和固定 Policy，也不能在进程退出后查看已经提交的 Run。

F-0005 负责接通最后一段 P1 用户路径：用户在终端启动文件任务，得到 Run ID、终态文本和 Artifact；
随后用同一个 SQLite 数据库查看 projection 和有序 Event。CLI 不再维护另一份状态，也不直接读取
SQLite 表。

## 2. 本次交付

- G-1：`bearagent run <objective>` 通过生产组装运行一个受限本地文件任务；
- G-2：`bearagent run inspect <run_id>` 显示状态、预算、usage、Activity、Error 和 Artifact；
- G-3：`bearagent run events <run_id>` 分页显示该 Run 已提交的有序 Event；
- G-4：人类输出和 `--json` 使用同一 application command 结果，JSON 具有稳定版本；
- G-5：真实 Provider、SQLite、workspace Tool 和固定 Policy 只在 composition root 组装；
- G-6：复用 F-0016 的五个固定任务，以注入式 Fake Provider 验证 production-compatible CLI 组装；
- G-7：完成 Feature 的工程文档、学习路径、开发者文档与公开状态同步，并保留 P1 收尾决定入口。

## 3. 本次不做

- NG-1：不增加 Checkpoint、启动恢复、pause/resume/cancel/retry、Attempt、Receipt 或 `UNKNOWN`；
- NG-2：不增加 Approval、Grant、sandbox、shell、代码执行、任意网络 Tool、HTTP API 或 Web UI；
- NG-3：不增加 Run 列表、删除、导出、全文搜索、交互式聊天或后台 daemon；
- NG-4：不增加第二个生产 Provider，不把 OpenAI SDK 类型暴露给 application 或 CLI；
- NG-5：不增加数据库 migration、Artifact 表或第二份 CLI 状态库；
- NG-6：不调用真实模型 API，也不把真实模型 4/5 设为本 Feature 的完成门槛；是否把它纳入 P1
  退出条件，等 F-0005 完成后由项目所有者另行决定；
- NG-7：不实时持久化 token delta，也不承诺进程中断后自动继续。

## 4. 需要先说明的约定

### Run profile 是可复现配置，不是密钥或权限

`bearagent run` 读取一个有大小上限、拒绝未知字段的 JSON Run profile。profile schema version 1 包含
现有 `AgentConfig` 和 `BudgetLimits`，因此模型、Prompt、Context、Tool 名单、定价和五类预算会随
`RunCreated` v2 Event 保存。

profile 不包含 API key、base URL、workspace 绝对路径或数据库路径。Provider 凭据和可选 endpoint
只从受信任进程环境注入；profile 中的 Tool 名单只能缩小暴露范围，不能绕过固定 Policy。

### inspect 是 projection 加 Event 证据，不是重新执行

`run inspect` 先通过 `EventStore.get_run` 取得 Reducer projection，再通过有界分页读取同一 Run 的
Event，提取已经保存的 Artifact 元数据。它不调用模型或 Tool，不解析日志，也不直接查询 SQLite 表。

### `--json` 是一个完整对象

每个命令的 JSON stdout 恰好包含一个 schema version 1 对象。进度和诊断只写 stderr，避免破坏机器
读取。`run events --json` 明确返回 Event payload；其中可能包含用户目标、模型输出和 ToolResult，
调用者应把它当作本地执行记录处理，而不是无敏感内容的日志摘要。

## 5. 使用场景

### 5.1 运行一个文件任务

用户准备非敏感 Run profile，并在环境中设置 Provider 凭据。用户指定 workspace、数据库和目标后，
CLI 初始化 SQLite，组装四个 workspace Tool、固定 Policy、OpenAI Responses adapter 和 `AgentLoop`。
人类输出在第一次 Provider 调用前给出 Run ID；终止时显示状态、模型文本、各 Tool Activity 和 Artifact
路径/hash。JSON 输出返回同一 `RunResult` 的稳定结构。

### 5.2 进程退出后检查事实

进程在一次模型或 Tool Activity 中退出。用户以先前显示的 Run ID 执行 `run inspect`。命令显示
`running` 和最后一个 PENDING/RUNNING Activity，而不是猜测成功。`run events` 仍能列出退出前已经提交
的 requested/started Event。

### 5.3 分页查看 Event

用户执行 `run events <run_id> --after-sequence 30 --limit 20 --json`。application command 校验参数，
调用 EventStore 的有界查询，并返回 sequence 31 开始的一页、下一游标和是否还有后续事实。

## 6. 必须满足的行为

### 6.1 Run 创建和生产组装

- FR-1：命令结构固定为 `bearagent run <objective>`、`bearagent run inspect <run_id>` 和
  `bearagent run events <run_id>`；三者均支持 `--json`；
- FR-2：执行命令默认使用当前目录作为 workspace、`data/bearagent.db` 作为 SQLite database、
  `data/p1-run-profile.json` 作为 version 1 Run profile，并允许分别用显式选项覆盖；workspace 必须是
  已有普通目录，profile 必须是有限 UTF-8 JSON 普通文件；
- FR-3：profile 只允许 `schema_version`、`agent_config` 和 `budget_limits`，并复用现有严格领域校验；
  API key、authorization、base URL、database 或 workspace root 出现在 profile 时必须因未知字段被拒绝；
- FR-4：生产 composition root 初始化 `SqliteEventStore`，创建 `OpenAIResponsesProvider` adapter，用
  同一个 `WorkspaceBoundary` 构造四个 workspace Tool，并以 profile 的 Tool 名单建立
  `FixedToolPolicy` 和 `ToolExecutor`；OpenAI SDK client 只在首个模型 Activity 开始时创建，模型不能改变
  这些对象；
- FR-5：CLI 在调用 Provider 前生成并显示 Run ID，再由 AgentLoop 使用该 ID 创建 Run；现有 Python
  调用不传 ID 时继续由 Loop 生成，不破坏 F-0016 用法；
- FR-6：执行结果只来自 `RunResult` 和已提交 `RunState`。成功时退出码为 0；Run 以 `failed` 终止或
  production boundary 安全失败时退出码为 1；Typer 用法错误保持退出码 2；
- FR-7：人类成功输出至少包含 Run ID、终态、最终模型文本、预算用量、Tool Activity 状态和每个
  Artifact 的规范化相对路径、字节数与 SHA-256；失败输出包含安全 Error，不打印原始异常；
- FR-8：`--json` stdout 只输出一个版本化结果对象。允许把 Run ID 和有限进度写入 stderr；不得把
  token delta、Provider 原始响应或完整 ToolResult 作为隐式日志输出。

### 6.2 inspect 和 events 查询

- FR-9：查询命令只通过 application query service 使用 `EventStore` port；不得导入 `sqlite3`、执行
  SQL、读取 projection row 或复制 Reducer；
- FR-10：`run inspect` 返回完整 `RunState`、终态 Error、预算 limits/usage、Activity 和从已提交 v2
  Tool completed Event 提取的 Artifact；非终态 Run 原样显示 `queued/running`；
- FR-11：inspect 的 Event 扫描必须分页且有可信总量上限。超过上限时返回明确安全错误，不能静默把
  不完整 Artifact 集合描述成完整结果；
- FR-12：`run events` 校验 UUID4 Run ID、`after_sequence` 和 `limit`，结果按 sequence 升序，单页
  不超过 EventStore 上限，并返回稳定 `next_after_sequence`/`has_more`；
- FR-13：Run 不存在时返回稳定的 not-found 错误和非零退出码；数据库不存在时查询不得创建一个空
  数据库冒充有效 Store；数据库 migration/corruption 错误只显示安全分类；
- FR-14：人类 events 输出默认只显示有限一行摘要；`--json` 才输出完整 Event 对象。两种输出都来自
  同一个 `EventPage`，不分别查询。

### 6.3 配置、输出和兼容

- FR-15：JSON result、inspection、Event page 和 safe command error 使用 Provider-neutral BearAgent
  类型并有 schema/快照测试；时间、Enum、UUID 和嵌套 Event 按 Pydantic JSON mode 序列化；
- FR-16：F-0005 不改变 v1/v2 Event 含义，不增加 SQLite migration。已有数据库可以直接 inspect；
- FR-17：`doctor`、`--version` 和 `python -m bearagent` 保持兼容，help 明确展示 Run 命令层级；
- FR-18：默认验证使用注入式 Fake Provider、临时 SQLite 和真实 workspace Tool 覆盖 CLI 全链，既不
  访问网络也不读取开发者环境中的真实 key；
- FR-19：F-0005 复用现有 OpenAI Responses adapter 的生产组装接口，但本 Feature 的测试、验收和收尾
  不发起真实模型请求；测试必须能注入 Fake Provider 而不建立第二套 CLI/application 路径；
- FR-20：F-0005 完成后，P1 仍保持 `进行中`，直到项目所有者单独决定真实模型 API/演练是否属于 P1，
  并完成其余 P1 Reality Check；不得由本 Feature 提前改写该决定。

## 7. 对外入口和模块连接

```text
Typer CLI
  -> application Run command / query service
     -> AgentLoop / EventStore port
        -> bootstrap 组装 OpenAI + SQLite + workspace Tool + fixed Policy
```

| 模块 | F-0005 的变化 |
|---|---|
| `domain` | 增加 Provider-neutral query/output 模型，供 application、CLI 和未来接口复用 |
| `application` | 增加执行 facade 与 Run inspect/Event page 查询；只依赖 domain、runtime 和 ports |
| `bootstrap.py` | 唯一生产 composition root；可以导入具体 Provider、SQLite 和 workspace adapter |
| `interfaces/cli` | 解析参数、读取有界 profile、选择 human/JSON renderer、映射退出码 |
| `adapters` | 复用现有实现；只做暴露 production 组装所需的窄改动 |
| `tests/evals` | 复用固定任务定义；增加显式凭据下的可选真实模型 runner |

`domain`、`runtime` 和 `application` 不导入 Typer、OpenAI SDK、SQLite 或 workspace adapter。CLI 不保存
第二份状态，bootstrap 不实现业务规则。

## 8. 状态和保存的数据

F-0005 继续使用 SQLite schema v1 和 Event payload v1/v2。执行命令创建的新 Run 由 F-0016 写 v2
Event；projection 仍由同一 transaction 内的 Reducer 更新。profile 的非敏感 AgentConfig、预算和目标
已经进入 `RunCreated`；profile 路径、workspace 绝对根、数据库路径、API key 和 base URL 不进入 Event。

查询输出不是新事实，不写 Event。Artifact 由已有 Tool execution Event 重建；本 Feature 不创建 Artifact
projection。回退后已有数据库和 `outputs/**` 保留。

## 9. 失败时会发生什么

- profile、workspace、Run ID 或分页参数无效：在 Provider/Tool 调用前拒绝；未创建 Run；
- 零模型预算：先保存 RunCreated/RunStarted，再以 `budget_exhausted` 终止；不创建 SDK client、不读取凭据；
- Provider 凭据缺失：首个模型 Activity 保存为 `provider_authentication` failure，Run 以同一安全 Error
  终止；不打印 key、endpoint 或 SDK 原始异常；
- 其他 client 配置无效：安全失败，不打印 endpoint 或 SDK 原始异常；
- SQLite 初始化失败：不调用 Provider；若 Run 尚未创建，不伪造 Run ID 对应的事实；
- Provider、Context 或预算失败：复用 AgentLoop 的安全 terminal Event 和 `RunResult`，退出码为 1；
- Tool 请求失败：仍按 F-0016 记录并交回模型；CLI 不绕过 Loop 提前重试；
- Ctrl+C/取消：`CancelledError` 原样传播，CLI 退出但不伪造 `RunFailed`；
- 强制退出：已经提交的 Event 保留，非终态 projection 不显示成功，也不自动继续；
- Tool 写入成功但 terminal Event append 失败：文件可能存在、Run 保持非终态；CLI 不猜测 Artifact 已被记录；
- 查询遇到 corruption、future migration 或 Event/Artifact 解析失败：整个查询安全失败，不展示部分结果
  为可信完整状态；
- stdout broken pipe 或 renderer 失败：不改变已经提交的 Run/Event，也不重试外部动作。

## 10. 安全与隐私

- CLI 不提供 `--api-key`，避免凭据进入 shell history 或进程参数；Provider 从环境读取凭据；
- profile 有 byte、UTF-8、JSON depth/node 和严格字段上限；它不能包含 adapter client 或授予权限；
- workspace 文件动作全部经过 Registry、prepare、FixedToolPolicy 和 ToolExecutor；CLI/bootstrap 不直接读写
  用户任务文件；
- 模型服务是唯一生产网络边界；P1 仍没有任意 HTTP/浏览器/MCP Tool；
- Run ID、database/profile/workspace 参数必须按各自边界校验。Error 不复制绝对根、SQL、原始异常、
  authorization 或 Provider response；
- `run events --json` 是用户显式请求的完整本地事实导出；默认 human 输出不打印 Event payload；
- CLI 不声称提供多用户隔离、加密数据库或 P3 sandbox。

## 11. 怎样检查执行过程

执行完成后，`run inspect` 展示 Reducer projection；`run events` 展示按 sequence 排列的 immutable facts。
用户可以把 Activity ID 与 ModelCallId/ToolCallId 对应起来，核对请求、开始、完成/失败、预算 usage、
Policy 决定和 Artifact hash。

CLI 自身只输出有限进度和安全诊断，不新增日志数据库。若 F-0005 完成后决定执行真实模型演练，必须
另存结构化、无凭据的结果摘要，并注明模型可用性和网络影响；它不能替代确定性 CI。

## 12. 上线与回退

使用 Fake Provider 注入和临时数据库验证 CLI。F-0005 不读取真实凭据、不运行真实模型演练，也不关闭
P1。没有服务端部署、feature flag 或 schema migration。

回退时可移除 F-0005 的 CLI/application/bootstrap 新代码和未发布的 profile 示例，但必须保留已有 v1/v2
Event 读取能力，不删除 `data/` 数据库或用户 `outputs/**`。若 CLI JSON 已发布后需要不兼容改变，使用新
schema version，不能静默改写 version 1。

## 13. 验收标准

- AC-1：给定合法 profile、临时 workspace、SQLite 和 Fake Provider，`bearagent run` 应只通过 production
  composition/application 路径完成任务，退出 0，并输出 Run ID、终态文本、Tool 状态和 hash 可核对 Artifact；
- AC-2：给定 Provider/Context/预算导致的 terminal failure，`bearagent run` 应退出 1，stdout/JSON 只含
  安全 Error；零预算不得创建 SDK client，缺少凭据应返回 `provider_authentication`，数据库中的 Event
  与 RunState terminal 结论一致；
- AC-3：给定同一数据库和 Run ID，`run inspect` 应返回与 `EventStore.get_run` 相同的 projection，并从
  已提交 Tool Event 返回完整 Artifact 元数据；非终态 Run 不显示成功；
- AC-4：给定多页 Event，`run events` 应按 sequence 返回有界页面、稳定游标和 `has_more`；非法 UUID、
  cursor、limit、缺失 Run 或超量 inspect 均明确失败；
- AC-5：当数据库不存在时，inspect/events 不创建空数据库；当数据库损坏或版本超前时，命令安全失败，
  不打印 SQL、绝对路径或原始异常；
- AC-6：当运行 `--json` 时，stdout 应只有一个 schema version 1 JSON 对象；human 与 JSON renderer 使用
  同一 application 结果，UUID/时间/Enum/Event payload 可稳定 round-trip；
- AC-7：当 profile 含未知/敏感字段、超大数据、非法 UTF-8 或越界配置时，命令应在任何 Provider/Tool
  调用和数据库写入前拒绝；CLI 参数和输出不包含 API key；
- AC-8：生产组装应只存在于 `bootstrap.py`，application/runtime/domain 不导入 adapter、SDK 或 Typer；
  所有 workspace 动作仍经过固定 Policy 和 ToolExecutor；
- AC-9：Ctrl+C 或强制中断后，已提交事实可由 inspect/events 查询，active Run 保持非终态；CLI 不自动
  retry、resume 或伪造 `UNKNOWN`；
- AC-10：`doctor`、`--version`、console script 和 `python -m bearagent` 回归通过；wheel 中包含 CLI、
  composition 和查询代码；
- AC-11：默认验证使用 Fake Provider 完成 5/5，不访问网络或真实凭据；production composition 的测试
  注入 Fake Provider，并证明不会读取开发者环境中的真实 key；
- AC-12：完整测试、Schema、Ruff、Pyright、文档链接、Starlight 和构建通过；Spec/Plan/Architecture、
  Roadmap、README、学习页、开发者页和状态页据实关闭 F-0005，但保持 P1 `进行中`，并记录真实模型
  API/演练和 P1 Reality Check 仍待后续决定。

## 14. 验证方式

- Unit：profile/参数边界、query service、Artifact 提取、pagination、renderer 和 exit code；
- Contract：Run query/output JSON schema、Event page round-trip、现有 Store/Provider/Tool contracts；
- Integration：Typer + Fake Provider + SQLite + 四个真实 workspace Tool；console script 和 module entrypoint；
- Recovery：RunCreated/Activity/terminal append 边界、Ctrl+C、外部写后 append 失败和重开查询；
- Security：profile secret 字段、Prompt 提权、Policy 旁路、路径/异常/SQL/SDK 脱敏、缺失/损坏数据库；
- Eval/manual：Fake 5/5；本 Feature 不读取真实凭据或调用真实模型 API。

## 15. 文档同步

- [x] Engineering source of truth：Spec、Plan、ADR、Architecture、Roadmap、README、CLI help；
- [x] Site beginner learning path：从运行命令到 inspect/events 的完整文件任务；
- [x] Site developer documentation：composition root、application query、JSON contract 和失败边界；
- [x] Site current status / milestone summary：关闭 F-0005，保持 P1 进行中，并写明真实模型/P1 Reality
  Check 待后续决定；
- [x] Architecture / ADR：生产组装和 CLI/application 依赖方向；
- [x] Deployment docs：本地数据/profile/环境凭据，不新增公开服务；
- [x] Generated reference：Run profile 与 CLI JSON schema/快照。

## 16. 已确认的决定

1. 使用 version 1 JSON Run profile 保存非敏感 `AgentConfig + BudgetLimits`；默认路径是
   `data/p1-run-profile.json`，workspace 默认当前目录，数据库默认 `data/bearagent.db`；三者可显式覆盖，
   API key/base URL 只从环境注入；
2. 保持路线图语法：`bearagent run <objective>`，并在同一 `run` 命令组下提供 `inspect/events`；
3. human events 默认只显示摘要；只有显式 `--json` 返回完整 Event payload；
4. 默认验证保持离线 Fake 5/5；F-0005 不调用真实模型 API，不以真实模型 4/5 为完成门槛；Feature
   完成后再单独决定真实模型 API/演练是否属于 P1，P1 在该决定与完整 Reality Check 前不关闭。

项目所有者于 2026-08-20 接受本 Spec 和以上四项决定，并授权开始实现。
