---
title: BearAgent Project Charter and Roadmap
status: accepted
version: 0.3
last_verified: 2026-08-11
---

# BearAgent 项目启动大纲与路线图

## 1. 项目使命

通用聊天产品擅长生成答案，但把长期任务真正交给 Agent 后，还必须回答：执行过什么、允许做什么、失败后从哪里继续。BearAgent 的使命是把这三件事做成可运行、可测试、可由个人维护的 Runtime。

一句话定位：

> BearAgent 是一个可检查、可恢复、权限外置的 local-first Agent Runtime，面向希望把长期文件与开发任务交给 AI、又不愿把权限和执行历史交给黑箱的个人开发者与高级用户。

详细目标用户、竞品边界与对外表达见[产品定位](product-positioning.md)。本 Roadmap 只负责阶段顺序、范围和验收证据。

## 2. 产品原则与首个任务域

### 2.1 产品原则

- **先闭环，后扩面**：先让一个 Provider、一个 Agent、有限文件 Tool 可靠工作，再增加模型、工具和角色。
- **先事实，后恢复**：P1 先证明执行事实可以持久化与检查；P2 才承诺进程重启后的安全恢复。
- **先边界，后自治**：所有 ToolRequest 都经过运行时策略边界；P3 再增加 Grant、Approval 和隔离 runner。
- **先证据，后宣传**：没有代码、测试和可复现演练支撑的能力只能标记为设计或规划中。
- **先单机，后分布式**：P0-P3 固定单用户、单 Agent、单进程、SQLite、CLI-first。

### 2.2 首个任务域

首个目标用户是项目作者本人，首个任务域是**限定 workspace 内的文件与技术研究/编码辅助**：

- 读取、列出和检索项目资料；
- 在 `outputs/**` 生成或替换文档、报告和代码 Artifact；
- 多轮调用模型与 Tool 完成一个可交付结果；
- 查看模型、Tool、预算、错误和 Artifact 的执行事实；
- P2 起在进程中断后从安全边界继续；
- P3 起在危险动作前申请精确批准，并把代码执行放进隔离 runner。

第一版完整闭环：

```text
P1 可检查执行
      ↓
P2 安全恢复
      ↓
P3 权限治理 + 隔离自托管
```

三个阶段必须依次关闭。P2 不能用“未来会有审批”代替当前恢复测试，P3 也不能用 sandbox 掩盖尚未解决的副作用恢复语义。

## 3. P3 项目完成线

P3 是第一个“小而完整”的产品完成线，而不是功能终点。关闭 P3 时必须同时满足：

- 10 个固定端到端 workspace 任务中至少 8 个无需修改代码完成；
- 在模型完成、workspace 写提交、等待审批三个安全边界强制结束进程后，Run 可按契约恢复且不重复已确认副作用；
- workspace 逃逸、prompt injection 提权、审批参数篡改和 host shell 四类安全测试全部阻断；
- 所有 Run 可导出 Event/trace，失败可定位到 Activity，无法确认的副作用显式进入 `UNKNOWN`；
- runner 无法读取 provider key、宿主根目录、主数据库和 Docker socket；
- Docker Compose 可在干净 Linux 环境部署，并从 SQLite + Artifact 备份恢复；
- 新开发者只依靠仓库文档即可解释核心术语、边界、失败语义和验证命令。

持续观察但不作为单次硬门槛的指标：任务成功率、人工接管率、每 Run token/费用、P50/P95 时长、Tool 成功/重试率、Approval 数量与等待时间、恢复延迟、`UNKNOWN` 数量以及文档/测试遗漏导致的回归数。

## 4. 总体节奏与阶段门

对于个人开发、AI 辅助且每周有稳定开发时间的情况，P0-P3 可暂按 **6-8 周 / 25-35 个专注开发日**控制范围。这不是交付承诺；阶段只由验收证据关闭。

| 阶段 | 产品承诺 | 主要风险 | 退出证据 |
|---|---|---|---|
| P0 Engineering Baseline | 仓库可以持续、安全地开发 | 边界和术语漂移 | 工程、架构、CI 和文档治理基线 |
| P1 Inspectable Execution | 一次真实本地 Run 有界、受限、可检查 | 无限循环、路径越界、事实缺失 | CLI 文件任务 + Activity/Event/Artifact 视图 |
| P2 Safe Recovery | 崩溃后从安全边界继续，副作用语义诚实 | 重复写、假 exactly-once、状态分叉 | kill-point、重建、幂等与 `UNKNOWN` 演练 |
| P3 Governed Self-hosting | 权限外置、代码隔离、单用户安全自托管 | 提权、审批重放、secret/host 暴露 | 安全测试 + runner + 备份恢复 + HTTPS |
| P4 Personal Agent Experience | 稳定内核上形成日常体验 | 过早堆集成 | Web、Skill、MCP、Memory 共用同一 Runtime |
| P5 Trace / Replay / Eval | 核心承诺可持续比较和公开证明 | 只评答案不评行为 | 可复现 eval、trace assertions 和发布证据 |

## 5. P0：Engineering Baseline

**状态：已完成（2026-08-09）。** 实现范围与证据见 [F-0000 P0 Engineering Baseline](../specs/F-0000-p0-engineering-baseline.md)。

### 目标与产物

让仓库具备可持续 AI 开发的最小骨架，统一术语、依赖方向、文档治理和验证命令：

- Python 3.12、uv、包边界、CLI `help/version/doctor`；
- Ruff、Pyright、pytest、跨平台 CI 和工程文档链接检查；
- domain/runtime/ports/adapters/interfaces 骨架；
- Fake Model、Fake Tool、In-memory EventStore；
- Architecture、Roadmap、Spec/ADR/Plan 模板与 AI 开发 SOP。

### 退出证据

- 干净环境可按 README 安装并运行检查；
- import boundary test 阻止 Runtime Core 导入外层框架；
- 新 Feature 可以按仓库规则完成 Spec、Plan、测试和文档关闭。

## 6. P1：Inspectable Execution

**状态：进行中（2026-08-10 开始）。** [F-0001 Domain IDs, messages and errors](../specs/F-0001-domain-ids-messages-errors.md)、[F-0002 Run reducer, Activity lifecycle and budgets](../specs/F-0002-run-reducer-activity-lifecycle-budgets.md) 与 [F-0015 Local Starlight documentation site](../specs/F-0015-local-starlight-docs-site.md) 已实现；下一个运行时 Feature 尚未确认。

### 6.1 阶段目标

本地 CLI 完成一次真实、受限、有界的 workspace 文件任务，并让用户能检查每个关键 Activity、Event、预算消耗、错误和 Artifact。

P1 的关键词是 **inspectable**，不是 resumable。进程崩溃后，已提交事实必须保留且不能伪装成功，但 P1 不自动续跑；安全恢复属于 P2。

### 6.2 详细范围

#### A. 领域状态与有界 Runtime

- 定义 Run/Activity 生命周期、事件 payload 和纯 reducer；
- 每次 Run 限制最大模型迭代、token、金额、wall time 和 Tool 次数；
- budget/deadline 在调度新 Activity 前检查，耗尽后产生稳定错误与终止事实；
- 第一版 Tool 串行执行，不并行调度，不引入 planner/reviewer 子角色。

#### B. 持久事实与查询

- EventStore contract 与 SQLite WAL adapter；
- `sessions/runs/events/activities/artifacts` schema，Event append 与 projection 更新在同一 transaction；
- 显式 SQL migration、schema version、从空库迁移测试；
- 完整模型响应、usage、Provider request ID、ToolRequest/ToolResult、错误和 Artifact metadata 落盘；
- token delta 只实时输出，不逐 token 写 WAL；崩溃时允许丢失未完成 stream。

P1 的 Event log 是可检查事实来源，不等于已经具备 Checkpoint 或 startup recovery。

#### C. Model Port 与 Agent Loop

- 内部 `ModelRequest/ModelEvent` 保持 Provider-neutral；
- 实现一个真实 Provider adapter，并用 Fake Provider 做确定性 Loop 测试；
- Adapter 负责 SDK 对象翻译、timeout、取消、usage 和错误分类；
- 只对明确临时错误做有界 retry，参数、权限和上下文超限不得盲重试；
- Prompt、Tool schema、Provider 与模型标识进入可比较 trace metadata，密钥不落盘。

#### D. Tool 与固定权限边界

- `ToolSpec/ToolRequest/ToolResult`、ToolRegistry 与统一 ToolExecutor；
- Tool 声明输入/输出 schema、side effect、timeout、输出上限和 retry semantics；
- `list_directory`、`read_file`、`search_files`；
- `write_file` 只允许在 `outputs/**` 原子创建或替换文件，并登记 Artifact hash/metadata；
- 路径 canonicalization 阻断绝对路径、`..`、symlink escape 和越界 rename；
- 读取、搜索、写入和错误文本都有大小上限，调用可超时。

P1 仍要求每个 ToolRequest 经过统一策略端口。其实现只有固定规则：允许限定读取和 `outputs/**` 写入，其余拒绝；P3 才增加可配置 Grant、`ALLOW/ASK/DENY` 和用户 Approval。

#### E. CLI 与可观察性

- `bearagent run` 启动一次 Run，并输出流式文本、Tool 状态和最终 Artifact；
- `run inspect` 显示 Run/Activity 状态、预算、usage、错误和 Artifact；
- `run events` 按 sequence 输出事件；
- 人类可读与 `--json` 输出共享同一 application command，不复制业务逻辑；
- 日志使用 correlation ID，默认不打印 secret、原始认证头或完整敏感 Tool 结果。

#### F. 文档与验证

- 为每个已实现 Feature 同步工程 Spec/Plan、初学者路径、开发者导读和当前状态；
- Event schema snapshot、Provider/Tool contract tests、SQLite integration tests、路径安全测试和 CLI 端到端测试；
- P1 关闭后再发布静态文档站；Agent Runtime 仍只在本机使用。

### 6.3 明确不做

- Checkpoint、startup recovery、pause/resume/cancel/retry command 和 `UNKNOWN` 处置；
- shell、代码执行、任意 HTTP、MCP、Memory、Web UI；
- 修改 workspace 中已有源码或输入文件；只允许写 `outputs/**`；
- 并行 Tool、多 Agent、多 Provider 兼容矩阵；
- 公开 HTTP 服务或服务器 Agent 部署。

### 6.4 推荐实现切片

1. **State**：F-0002 Run reducer、Activity lifecycle 与 budgets；
2. **Facts**：F-0003 EventStore contract、SQLite、projection 与 migration；
3. **Effects**：F-0006 Tool contract/registry/baseline policy gate，F-0007 只读工具，F-0008 原子写与 Artifact；
4. **Intelligence**：F-0004 第一个真实 ModelProvider 与 bounded Agent Loop；
5. **Product path**：F-0005 `run/inspect/events` CLI 与端到端演示。

每次只激活一个主 Feature。Feature 可按依赖重新排序，但不能绕过前置契约或并行铺开全部 Backlog。

### 6.5 旗舰 Demo

```powershell
bearagent run "阅读 docs 下的架构、产品定位和 SOP，生成一份不超过 800 字的项目介绍到 outputs/intro.md"
bearagent run inspect <run-id>
bearagent run events <run-id> --json
```

演示必须同时展示一次非法路径请求被拒绝，以及一次低预算 Run 明确终止。

### 6.6 P1 退出门槛

- 真实模型成功完成旗舰 Demo，生成带 hash 的 Artifact；
- 非法路径、symlink escape、超大读写和超时被结构化拒绝；
- 每个模型/Tool Activity 可由 `inspect` 关联到有序 Event；
- budget 耗尽不会继续调度新 Activity；
- Event append 与 projection 在故障下不会出现已提交 projection 却缺少事实的分叉；
- 进程意外退出后，已提交 Event 仍可查询，非终态 Run 不会被展示为成功；
- schema snapshot、迁移、contract、integration 与 security tests 通过；
- 当前状态页明确写出“尚不支持恢复、Approval 与 sandbox”。

## 7. P2：Safe Recovery

**状态：未开始。** 必须在 P1 关闭后启动。

### 7.1 阶段目标

把 P1 的“事实可查”升级为“从事实安全继续”：进程可以退出、取消或重试，但已确认副作用不会被无脑重复，无法判断的结果会诚实暴露给用户。

### 7.2 详细范围

#### A. 可重建状态与 Checkpoint

- 纯 reducer 从完整 Event stream 重建同一 RunState；
- Checkpoint 记录 event sequence、schema/version、state hash 和创建原因；
- 启动时校验 Checkpoint 后加载 event tail；损坏、版本不兼容或缺失时回退到完整 replay；
- Checkpoint 是优化，不是事实来源，删除后不改变语义；
- migration 覆盖空库和至少一个前一版本，并提供失败回滚/恢复说明。

#### B. Recovery Coordinator

- 启动时扫描非终态 Run，并按最后一个持久安全边界分类；
- 未完成模型 stream 可以使用相同持久上下文重新请求，但不承诺 token 一致；
- 已完成 Tool Activity 不重复执行，结果重新注入下一次模型上下文；
- 正在执行的 Activity 依据 side-effect/retry contract 进入安全重试、reconcile 或 `UNKNOWN`；
- 恢复决策本身写入 Event，用户可以解释“为什么继续、重试或停住”。

#### C. pause / resume / cancel / retry

- application commands 记录意图，再由 Runtime 协作式传播给 Model/Tool adapter；
- cancel 后不得调度新 Activity；已在外部执行的动作仍按 receipt/`UNKNOWN` 处理；
- retry 必须创建新尝试并关联原 Activity，不覆盖旧事实；
- pause/resume 只发生在持久边界，不序列化 Python 协程或调用栈；
- 重复 command 应幂等或返回稳定冲突，不造成双重状态转换。

#### D. 副作用与不确定性

- 每个 mutating Activity 有 idempotency key、attempt 和可选 receipt；
- 原子 workspace write 使用同目录临时文件、flush/replace 和 content hash 进行 reconcile；
- 纯读可以在次数与 deadline 内自动重试；
- 支持幂等键的写用同一键查询或重试；
- 无幂等接口、无 receipt 且无法查询的外部写进入 `UNKNOWN`，等待人工决定；
- 不以“最终成功”覆盖中间发生过的 uncertain/failed attempts。

#### E. Trace 与故障注入

- 导出/导入 golden trace，包含版本、Event、命令和可重放的 adapter 输入；
- 提供确定性 clock、ID、Fake Provider/Tool 和 kill hooks；
- recovery tests 检查最终状态、Event sequence、Activity attempt 和副作用计数；
- 记录恢复次数、延迟、原因和 `UNKNOWN` 数量。

### 7.3 恢复矩阵

| Activity 类型 | 重启后的默认动作 |
|---|---|
| 未完成模型 stream | 从前一持久边界重新请求，受预算与 retry 限制 |
| 纯读 Tool | 自动重试，创建新 attempt |
| 已确认成功的 Tool | 不重复，复用已持久 ToolResult |
| workspace 原子写 | 根据目标文件、临时文件和 content hash reconcile |
| 支持幂等键的远程写 | 使用同一键查询或重试 |
| 无法确认的外部写 | 标记 `UNKNOWN`，禁止自动假定成功或失败 |

P2 产品中仍不注册任意远程写或 shell；后两行先通过 Port contract、Fake adapter 和恢复测试固定语义，供后续能力复用。

### 7.4 故障演练

P2 至少在以下位置强制结束 runtime：

1. `ModelCallRequested` 已提交、`ModelCallCompleted` 未提交；
2. `ToolCallCompleted` 已提交、下一次 `ModelCallRequested` 未提交；
3. workspace 临时文件写入后、原子 replace 前；
4. cancel 意图已提交、adapter 尚未确认停止；
5. projection transaction 回滚后以及 Checkpoint 写入损坏时。

“等待 Approval 时崩溃”不属于 P2 演练，因为 Approval 在 P3 才实现；它将作为 P3 的持久权限门测试。

### 7.5 明确不做

- Grant/Approval、shell/code runner、公开 HTTP API；
- 任意 Python 栈、协程或 token stream 的字节级恢复；
- 对不可查询外部副作用承诺 exactly-once；
- 多 worker lease、分布式 queue、Temporal/Celery；
- 为了演示恢复而提前引入 P3/P4 Tool。

### 7.6 旗舰 Demo

运行 P1 文件任务，在每个 kill point 结束进程并重新启动：

- 已完成 read/write Activity 不重复；
- 未完成的安全 Activity 创建可解释的新 attempt；
- 删除 Checkpoint 后得到同一 RunState；
- 模拟不可确认写时 Run 停在可见的 `UNKNOWN`，由人工命令解决而不是自动猜测。

### 7.7 P2 退出门槛

- 所有故障演练在 Windows 本地和 Linux CI/容器环境通过；
- Event-only replay 与 Checkpoint + tail 得到等价状态和 hash；
- 已确认 workspace 写不重复，临时文件与目标文件可正确 reconcile；
- cancel 后没有新 Activity，重复 cancel/retry 不制造重复转换；
- `UNKNOWN` 有查看、人工解决和审计路径；
- 从空库与前一 schema version 的 migration/recovery 测试通过；
- golden trace 可由 Fake adapters 重放并断言 Activity/side-effect 次数；
- P2 完成后才建立仅通过 SSH tunnel 或私有网络访问的服务器 staging。

## 8. P3：Governed Self-hosting

**状态：未开始。** 必须在 P2 恢复语义关闭后启动。

### 8.1 阶段目标

把可恢复 Runtime 升级为单用户安全自托管 beta：权限不由模型决定，高风险请求需要精确审批，代码执行与主 Runtime、secrets 和宿主隔离，部署可以备份与恢复。

P3 的关键词是 **authority-first**。Sandbox 是纵深防御，不代替 Policy；Approval 是用户决策，不代替参数校验；认证只确认“谁在请求”，不自动授予任意 Tool 权限。

### 8.2 详细范围

#### A. Grant、Policy 与 Approval

- Grant 表达 `principal + action + resource + constraints`，默认拒绝；
- ToolRequest 在执行前 canonicalize，并由 PolicyEngine 返回 `ALLOW / ASK / DENY`；
- Approval 绑定 `run_id + tool_call_id + canonical_args_hash + expiry + one-time nonce`；
- 修改路径、命令、环境、网络范围或其他 canonical args 后，旧 Approval 失效；
- Approval request/resolution、Policy decision 与匹配 Grant 都写入 Event；
- Prompt、Skill、模型输出、Tool 输出和 workspace 文件不能创建或扩大 Grant；
- P1 固定策略作为默认最小配置保留，配置错误不得 fail open。

#### B. 持久审批与恢复

- `WAITING_APPROVAL` 是可持久 Run 状态，重启后仍等待同一精确请求；
- 过期、已使用、被拒绝或参数变化的 token 不可重放；
- cancel 可以终止等待中的 Run；重复 resolution 返回稳定结果；
- 审批后、Tool 开始前和副作用提交后的 kill point 分别按 P2 语义恢复；
- 用户可从 CLI/API 查看批准内容、风险、资源范围和结果 receipt。

#### C. Sandbox runner

- shell/code Tool 只通过 `SandboxBackend` 调用独立 runner sidecar；
- rootless/unprivileged、read-only rootfs、scoped per-Run workspace；
- CPU、memory、PID、wall-time、stdout/stderr 和 Artifact 大小限制；
- network 默认拒绝，放行必须是独立 Grant/Policy 约束；
- runner 不挂 provider key、主数据库、宿主根目录、用户 home、1Panel 目录或 Docker socket；
- runner RPC 验证调用身份、request ID/nonce 与 deadline；
- runner 不可用时 Tool 不注册或明确失败，永不回退到 host subprocess。

#### D. HTTP API 与 SSE

- FastAPI 位于 Interface/Adapter 层，调用与 CLI 相同的 application commands；
- 提供 Run 创建、查询、Event/SSE、Approval resolution、cancel/retry 和 Artifact 下载的最小 API；
- SSE 支持 event sequence/`Last-Event-ID` 续接，不能只依赖内存 token stream；
- 单用户认证、Secure/HttpOnly/SameSite session、CSRF、防暴力/rate limit 和请求体上限；
- API 错误使用安全领域错误，不回传 stack、secret 或原始敏感 ToolResult；
- P3 只交付 headless API/CLI beta，Web UI 仍属于 P4。

#### E. 自托管与运维

- Docker Compose 包含 Runtime API 与 runner，使用固定镜像版本、healthcheck 和 restart policy；
- API 只绑定 loopback 或 private container network，由 1Panel/OpenResty 终止 TLS；
- `agent.bearguin.cn` 使用 HTTPS 与应用认证，文档站独立部署；
- SQLite 使用 online backup/受控 checkpoint，连同 Artifact 与非 secret 配置备份；
- 在空目录执行 restore drill，记录 hash、schema version 和恢复步骤；
- security/recovery runbook 覆盖密钥轮换、runner 故障、`UNKNOWN`、备份恢复和回滚。

#### F. 威胁与验证

- path traversal、symlink escape、TOCTOU；
- prompt injection 请求提权或绕过审批；
- Approval 参数替换、过期、重放和跨 Run 使用；
- shell escape、环境变量/secret 泄漏、超大/无限输出；
- runner 访问宿主、Docker socket、主数据库或 provider key；
- SSE 重连丢事件、认证绕过、CSRF、rate limit 失效；
- 服务重启造成重复副作用或等待审批状态丢失。

### 8.3 明确不做

- Web UI、MCP、Skills、Memory、浏览器/电脑控制和任意通用网络访问；
- 多用户、组织 RBAC、计费、插件市场；
- 给 runner 挂宿主 Docker socket、完整仓库或 Runtime secrets；
- host subprocess fallback；
- Kubernetes、PostgreSQL、Redis、queue 或多 worker；
- “sandbox 内即可自动允许”的隐式授权。

### 8.4 旗舰 Demo

1. 通过已认证 CLI/API 启动一个 workspace Run；
2. 安全读取由最小 Grant 自动允许，高风险代码执行进入 `WAITING_APPROVAL`；
3. 篡改一个参数后复用 Approval，Policy 明确拒绝；
4. 使用原参数批准，Tool 只在 runner 中执行且读取不到 provider key/宿主目录；
5. 在等待审批、批准后未执行、执行结果未持久化三个位置重启服务；
6. 检查恢复决定、receipt/`UNKNOWN`、Event trace 与 Artifact；
7. 备份 SQLite + Artifact，在空目录恢复同一 Run 记录。

### 8.5 P3 退出门槛

- P3 项目完成线的任务、恢复、安全、隔离、可观察与文档指标全部满足；
- Policy 默认拒绝，所有 Tool 都无法绕过统一 executor；
- Approval 精确绑定、一次性、可过期且跨重启有效；
- runner 不可用时无 host fallback，资源/网络/secret 隔离测试通过；
- CLI 与 API 操作同一 Run 和同一命令路径；SSE 重连能从持久 sequence 补齐；
- `agent.bearguin.cn` 仅通过 HTTPS 和认证访问，内部端口不直接暴露公网；
- 备份在空目录真实恢复，Run/Event/Artifact hash 与审计记录一致；
- 所有限制和非目标已同步 README、工程文档、学习路径、开发者文档与公开状态页。

## 9. P4：Personal Agent Experience

**状态：未开始。**

### 目标

在不破坏 P1-P3 内核的前提下，让 BearAgent 变成每天能用的个人 Agent。

### 功能

- 最小 Web UI：Session/Run、stream、Approval、Artifact、trace；
- Skill loader 和版本化 manifest；
- MCPToolProvider，按 server/tool 授权；
- 文件型 episodic/profile Memory，带 provenance/confidence/expiry；
- SQLite FTS5 检索；
- ContextBuilder token budget、可恢复压缩和 todo recitation；
- 基础 HTTP fetch/search（单独 Grant、SSRF 防护）；
- Provider 配置体验和成本显示。

### 验收

- 新 Skill 不改 Runtime 代码即可加载；
- MCP Tool 与内置 Tool 走同一 Policy/Event/ToolResult；
- 用户能查看某条 Memory 的来源并删除；
- 长任务压缩后仍可通过文件/Event reference 恢复关键证据；
- Web 和 CLI 操作同一 Run，不存在两套业务逻辑。

## 10. P5：Trace、Replay、Eval 与公开证据

**状态：未开始。**

### 目标与功能

把个人可用 Runtime 升级为有工程与研究说服力的 Agent Infra 项目：

- OpenTelemetry traces 和 metrics；
- eval dataset、grader、trace assertions；
- 模型/Prompt/Skill/Tool 版本对比；
- replay with fake adapters；
- cost/latency/success dashboard；
- chaos/recovery benchmark；
- architecture deep dives、进阶 tutorial、release notes 和文档版本治理；
- public security model 和 responsible disclosure。

### 验收

- 固定 eval 在 CI/nightly 可复现；
- 修改 Prompt/模型/Tool schema 时可以看到答案与执行轨迹回归；
- 文档中每个核心承诺有代码/测试证据链接；
- `docs.bearguin.cn` 随 release 构建并持续区分当前实现与规划能力。

## 11. P6+：只有需求证明后再做

**状态：候选范围，未排期。**

- Child Run 形式的 Multi-Agent：独立 budget、Grant、Checkpoint 和 trace；
- schedules/webhooks/long timers；
- browser/computer use；
- hybrid/vector RAG；
- 消息渠道；
- PostgreSQL、多 worker、queue、lease；
- Temporal 或其他 durable workflow engine；
- 多用户和租户隔离。

进入任一项前都要给出触发证据，例如“SQLite 写入争用达到阈值”“有跨天 timer”“需要三台 worker”，而不是因为参考项目已经支持。

## 12. 第一批 Feature Backlog

`F-NNNN` 是全项目稳定 ID。下列未创建 Spec 的名称只是规划映射；开始实现前必须创建 Feature Spec，并在 Front Matter 写入 `milestone`。阶段调整只修改 `milestone` 与本节归组，不重编号。

### P1：Inspectable Execution

1. [F-0001 Domain IDs, messages and errors](../specs/F-0001-domain-ids-messages-errors.md) — implemented
2. [F-0002 Run reducer, Activity lifecycle and budgets](../specs/F-0002-run-reducer-activity-lifecycle-budgets.md) — implemented
3. F-0003 EventStore contract, SQLite adapter and projections
4. F-0004 ModelProvider contract, first adapter and bounded loop
5. F-0005 CLI run/inspect/events
6. F-0006 Tool contract, registry, executor and baseline policy gate
7. F-0007 Workspace boundary and read tools
8. F-0008 Atomic write tool and artifacts
9. [F-0015 Local Starlight documentation site](../specs/F-0015-local-starlight-docs-site.md) — implemented

### P2：Safe Recovery

1. F-0009 Checkpoint, replay and startup recovery
2. F-0010 Pause/cancel/retry/idempotency/receipt/`UNKNOWN`

### P3：Governed Self-hosting

1. F-0011 Grant, Policy and durable Approval
2. F-0012 Sandbox runner and code Tool
3. F-0013 HTTP API/SSE/auth
4. F-0014 Compose, hardening, backup and restore

如果任何条目在编写 Spec 时无法形成一个可独立验收的 Feature，应保留现有 ID 的核心范围，并用新的全局 ID 拆出后续 Feature。不要让一个 Plan 同时实现整个阶段。

## 13. 文档与阶段治理

- 每个 Feature 完成时，必须同步工程 `docs/`、站点初学者路径、站点开发者文档和公开当前状态；
- 每个阶段关闭时，必须额外同步本 Roadmap、学习地图、开发者架构总结和阶段结果；
- 外部 Agent 项目只用于解释概念和设计对照；BearAgent 当前能力只由本仓库的 Spec、代码、测试和验收证据确认；
- 始终只维护 1 个 active 主 Plan；可并行处理至多 1 个不干扰主 Feature 的小修复；
- 阶段状态不能根据开发天数或主观完成度关闭，只能根据退出门槛。

## 14. 项目名称与对外叙事

项目名继续使用 **BearAgent**，Python package 使用 `bearagent`。暂时不拆出 BearRuntime 子品牌。

对外 README 与演示按以下顺序叙述：

1. 普通 Agent loop 为什么无法回答执行事实、权限和恢复问题；
2. BearAgent 的 P1/P2/P3 如何依次证明可检查执行、安全恢复和权限外置；
3. 一个从受限执行、crash/resume 到 Approval/sandbox 的真实演示；
4. 如何本地运行与安全自托管；
5. 哪些能力故意后置，以及当前版本尚未实现什么。

这比“支持多少模型、工具、Memory 或 Agent 角色”更能体现 BearAgent 的长期价值。
