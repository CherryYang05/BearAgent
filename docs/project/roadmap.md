---
title: BearAgent Roadmap
status: accepted
version: 0.12
last_verified: 2026-08-23
---

# BearAgent 项目路线图

## 1. 路线图怎样使用

BearAgent 按用户能够复现的结果推进，不按文件数量或开发天数关闭阶段。前三个阶段始终使用同一组
仓库与本地文档任务：先完成并看清过程，再处理中断，最后接入权限与隔离。

```text
P1 任务能完成，过程能查看
           ↓
P2 中断后只从能确认的位置继续
           ↓
P3 危险操作获准后在隔离环境执行
```

每个阶段都必须同时满足真实任务、失败演练、文档和测试。模块存在、ADR 被接受或架构图已经画出，
都不能替代阶段结果。

产品定位见[产品定位](product-positioning.md)，模块连接和长期边界见[总体架构](../architecture/overview.md)。

## 2. 固定产品范围

首个任务是仓库与本地文档研究：在指定 workspace 内查找和比较资料，并把报告或说明写入
`outputs/**`。P1 的文件 Tool 不联网，也不修改已有源码和输入文件；只有显式选择的模型 adapter
可以访问配置的 HTTPS endpoint。

P0 至 P3 固定为单用户、单 Agent、单进程、SQLite 和 CLI 优先。所有外部动作经过统一 Tool
executor；主 Runtime 进程不执行模型生成的 shell。Web、MCP、Memory、多个 Agent 和分布式 worker
不会抢在执行、恢复和权限闭环之前。

## 3. 阶段总览

| 阶段 | 状态 | 用户得到什么 | 关闭阶段的关键证据 |
|---|---|---|---|
| P0 工程基础 | 已完成 | 仓库可安装、测试，边界和开发流程明确 | 干净安装、CLI、CI、依赖边界、文档规则 |
| P1 可检查执行 | 已完成 | 固定本地文件任务可完成，过程和失败可查看 | Fake 5/5、真实 5/5、路径拒绝、预算终止、完整 Event |
| P2 失败恢复 | 未开始 | 中断后只从能确认的位置继续 | kill point、状态重建、不重复写入、`UNKNOWN` |
| P3 权限与隔离 | 未开始 | 危险操作获准后执行，代码与宿主隔离，可安全自托管 | Approval 篡改测试、runner 隔离、备份恢复、HTTPS |
| P4 日常使用 | 未开始 | Skill、MCP、Web 和 Memory 依次接入 | 新入口不绕过原有记录和权限路径 |
| P5 持续评测 | 未开始 | 可以比较质量、成本、恢复和安全回归 | 固定数据集、执行路径断言、跨版本报告 |

P3 是第一个可信 Runtime 完成线，不是成熟通用 Agent 产品完成线。

## 4. P0：工程基础

**状态：已完成（2026-08-09）。** 详细验收见 [F-0000](../specs/F-0000-p0-engineering-baseline.md)。

### 交付结果

- Python 3.12、uv、包结构和 lockfile；
- `help`、`version`、`doctor` 命令；
- Ruff、Pyright、pytest、Windows/Ubuntu CI 和文档链接检查；
- domain/runtime/ports/adapters/interfaces 模块边界；
- Fake model、Fake tool、内存 Event store；
- Architecture、Roadmap、Spec/ADR/Plan 模板和开发流程。

### 完成证据

干净环境可以按 README 安装并运行全部检查；architecture test 会阻止 Runtime 导入外层框架；新
Feature 可以根据 Spec、Plan、测试和文档流程推进。

## 5. P1：可检查执行

**状态：已完成（2026-08-23）。** F-0001 至 F-0008、F-0015、F-0016 和 F-0017 均已实现。
F-0017 交付直接填写本机 key、拒绝 pricing 且被 Git 忽略的 config v1、RunProfile v2、三种协议
adapter、Event v3 和默认关闭的 live runner。suite v1.1.1 又通过 production composition 完成四个
普通任务与安全 canary；最终离线 Reality Check 和脱敏报告均已完成。

### 5.1 用户结果

命令行可以启动仓库与本地文档研究 Run。Agent 读取指定 workspace，并向 `outputs/**` 生成结果。
用户可以查看每次模型和 Tool Activity、预算、Error 和 Artifact。

P1 只承诺已经保存的事实可查。进程退出后不自动继续，未完成的 Run 也不能显示为成功。

### 5.2 需要接通的路径

#### 状态和预算

- Run/Activity 生命周期和具体 Event；
- 纯 Reducer 从 Event 计算状态；
- 模型次数、Tool 次数、token、费用和总时间预算；
- P1 同时最多一个 active Activity。

F-0002 已完成这一部分。

#### Event 保存和查询

- Event store port、SQLite WAL adapter 和显式 SQL migration；
- Event 追加与 projection 更新在同一 transaction；
- 保存完整模型响应、usage、Provider request ID、ToolRequest/ToolResult、Error 和 Artifact 元数据；
- token delta 可以实时输出，但不逐 token 写 WAL。

P1 的 Event log 用于检查事实，不包含 Checkpoint 或启动恢复。

F-0003 已完成 EventStore port、SQLite adapter、schema v1 和 projection。正常重开数据库后仍能
查询已提交事实，但 Runtime 不会自动扫描或继续非终态 Run。

#### 模型和 Agent Loop

- 三种显式 wire protocol adapter，外部 SDK 对象在边界翻译；
- 一个配置只选择一个 adapter，不检测厂商，也不 fallback；
- Fake Provider 驱动确定性 Loop 测试；
- ContextBuilder 按稳定顺序组织 Runtime 规则、目标、必要消息、Tool schema 和 ToolResult；
- Context 和 ToolResult 有明确字符/byte 上限，大结果使用确定性 preview；
- Agent Loop 有明确结束条件，并在每次 Activity 前检查预算；
- Prompt、模型、Tool schema 和 Agent 配置版本进入 trace，密钥不保存。

P1 不做自动摘要 Memory 或复杂上下文压缩。

F-0004 已完成 Provider-neutral 模型数据与 port、确定性测试 adapter 和首个 OpenAI Responses 流式
adapter。F-0017 又实现 OpenAI Chat Completions 与 Anthropic Messages adapter，并由 `bootstrap.py`
按 catalog 的显式 protocol 选择一个生产 adapter。三个 adapter 共享 contract/security 测试，缺 usage、
未知关键流事件、不完整 ToolCall 或无法安全表示的隐藏 reasoning 都失败。真实 gate 证据已通过脱敏复核。

#### 受限文件工具

- `ToolSpec`、`ToolRequest`、`ToolResult`、Registry 和统一 Tool executor；
- 目录列出、文件读取、内容搜索；
- `write_file` 只向 `outputs/**` 原子创建或替换文件；
- 路径规范化拒绝绝对路径、`..`、symlink 逃逸和越界 rename；
- 输入、输出、时间和错误文本均有上限。

P1 的 Policy 是固定允许/拒绝规则。用户 Approval 属于 P3。

F-0006 已完成有界 Tool 数据、精确 Registry、默认拒绝 Policy 和统一 ToolExecutor。F-0007 已完成
`workspace.list`、`workspace.read`、`workspace.search` 和跨平台路径边界。F-0008 已完成只写
`outputs/**` 的 `workspace.write`、同目录原子提交和 Artifact 元数据。F-0016 已让 AgentLoop 只调用
ToolExecutor 的记录式入口，并把原始/规范化请求、Policy 决定和 ToolResult 写成 v2 Event。

#### CLI 和固定任务

- `bearagent run` 启动 Run，并输出模型文本、Tool 状态和最终 Artifact；
- `run inspect` 显示状态、预算、usage、Error 和 Artifact；
- `run events` 按 sequence 输出事实；
- 人类输出与 `--json` 调用同一 application result；
- 固定任务集记录任务版本、模型、Prompt、Tool 版本、预算、结果和执行路径。

F-0016 已交付五个版本化 Fake Provider 任务，并在内存/SQLite Store 上验证 5/5。F-0005 让相同任务
再通过 production composition、真实 SQLite 和 workspace Tools 验证 5/5，并接通 CLI/query 输出。
F-0017 让 Fake 与 live runner 共用 objective、fixture、预算和确定性 rubric；每个真实任务使用独立
workspace/SQLite，并在完成后重开查询。客户端只在首个模型 Activity 创建，因此零预算和缺少所选
凭据都会留下明确结果。live preflight 未通过时不会创建数据库、workspace、SDK client 或 Run。

### 5.3 P1 明确不做

- Checkpoint、启动恢复、pause/resume/cancel/retry、Attempt、Receipt 和 `UNKNOWN`；
- shell、代码执行、任意 HTTP、MCP、Memory、Web UI 和自动历史摘要；
- 修改 workspace 中已有源码或输入文件；
- 并行 Tool、多个 Agent 或多 Provider 兼容矩阵；
- 公开 HTTP 服务和 Agent 服务器部署。

### 5.4 推荐 Feature 顺序

1. F-0002：Run/Activity 状态、Reducer 和预算——已实现；
2. F-0003：Event store、SQLite、projection 和 migration——已实现；
3. F-0004：模型接口和首个真实 adapter——已实现；
4. F-0006：Tool 接口、Registry、executor 和固定 Policy——已实现；
5. [F-0007：workspace 边界和只读工具](../specs/F-0007-workspace-read-tools.md)——已实现；
6. [F-0008：`outputs/**` 原子写和 Artifact](../specs/F-0008-atomic-output-artifacts.md)——已实现；
7. [F-0016：ContextBuilder、有界 Loop、版本化 Agent 配置和任务集](../specs/F-0016-bounded-context-agent-loop.md)
   ——已实现；
8. [F-0005：`run/inspect/events` CLI 与端到端演示](../specs/F-0005-run-inspect-events-cli.md)——已实现；
9. [F-0017：用户配置模型协议与 P1 live gate](../specs/F-0017-configurable-model-providers-live-gate.md)
   ——已实现；真实 suite v1.1.1 通过 5/5。

每次只激活一个主 Feature。可以根据依赖调整顺序，但不能并行铺开整个 Backlog。

### 5.5 旗舰任务

```powershell
bearagent run "阅读 docs 下的架构、产品定位和 SOP，生成一份不超过 800 字的项目介绍到 outputs/intro.md"
bearagent run inspect <run-id>
bearagent run events <run-id> --json
```

任务集还要覆盖多文档汇总、带来源的差异比较和已有输出的受控替换。演示同时展示非法路径请求被
拒绝，以及低预算 Run 明确失败。

### 5.6 P1 退出证据

- Fake Provider 完成 5/5 固定任务，并断言预期工具路径和终止原因；
- 一个显式选择的真实配置完成四个普通任务和一个安全 canary，无需修改代码、Prompt 或 rubric；
- live preflight 固定 Provider、model、pricing snapshot、commit 和 suite cost cap，并在调用前显示最坏估算；
- 每个 Artifact 有 hash，任务失败可以从记录复现；
- 路径逃逸、超大读写和 timeout 产生结构化拒绝；
- 每个 Activity 可由 `inspect` 关联到有序 Event；
- 预算耗尽后不再请求新 Activity；
- transaction 故障不会出现 projection 已提交而 Event 缺失；
- 进程退出后已提交 Event 可查询，非终态 Run 不显示成功；
- schema、migration、contract、integration、security 和站点构建通过；
- 状态页明确写出 P1 尚不支持崩溃恢复、Approval 和代码隔离。

## 6. P2：失败恢复

**状态：未开始。P1 已关闭；开始 P2 前仍需接受对应 Feature Spec。**

### 6.1 用户结果

进程退出、取消或重试后，BearAgent 根据已保存 Event 决定下一步。已确认成功的 Tool 不重复执行；
安全的未完成操作可以创建新 Attempt；结果无法确认时停在 `UNKNOWN`。

### 6.2 交付范围

#### 状态重建

- 从完整 Event 重建同一 RunState；
- Checkpoint 保存 sequence、版本和 state hash，只用于加速；
- Checkpoint 缺失、损坏或不兼容时回到完整 Event；
- 从空库和至少一个旧 schema version 迁移。

#### 恢复决定

- 启动时扫描非终态 Run，并按最后一个已保存边界分类；
- 未完成模型 stream 从前一边界重新请求，不承诺相同 token；
- 已完成 Tool 复用结果，不重复执行；
- 未完成 Activity 根据副作用说明选择重试、reconcile 或 `UNKNOWN`；
- 恢复决定本身写成 Event，用户能看出为什么继续或停下。

#### 控制命令

- pause、resume、cancel、retry 先记录意图，再向 adapter 传播；
- cancel 后不再调度新 Activity；
- retry 创建新 Attempt，不覆盖旧记录；
- 重复命令必须幂等或返回稳定冲突。

#### 写入结果核对

- 每个写 Activity 有幂等键、Attempt 和可选 Receipt；
- workspace 原子写通过临时文件、目标文件和 hash reconcile；
- 纯读在次数和 deadline 内自动重试；
- 支持幂等键的远程写用同一键查询或重试；
- 无法查询且没有 Receipt 的外部写进入 `UNKNOWN`。

### 6.3 故障演练

至少在以下位置强制结束 Runtime：

1. 模型请求 Event 已保存、完成 Event 未保存；
2. Tool 完成 Event 已保存、下一次模型请求尚未保存；
3. workspace 临时文件写完、原子 replace 之前；
4. cancel 意图已保存、adapter 尚未停止；
5. projection transaction 回滚，以及 Checkpoint 损坏。

等待 Approval 的中断属于 P3，因为 P2 尚未实现 Approval。

### 6.4 P2 明确不做

Grant/Approval、shell runner、公开 API、任意调用栈或 token stream 的字节级恢复、不可查询外部写的
exactly-once、多 worker 和通用 workflow engine。

### 6.5 P2 退出证据

- Windows 和 Linux 上全部故障演练通过；
- Event-only 与 Checkpoint + tail 得到等价状态和 hash；
- 已确认 workspace 写不重复，临时文件可正确 reconcile；
- cancel 后没有新 Activity，重复命令不制造重复转换；
- `UNKNOWN` 有查看、人工处理和审计入口；
- migration/recovery 测试覆盖空库和旧版本；
- golden trace 可以用 Fake adapter 重放并断言副作用次数。

P2 完成后才建立只通过 SSH tunnel 或私有网络访问的服务器 staging。

## 7. P3：权限、隔离与自托管

**状态：未开始。必须在 P2 恢复闭环完成后启动。**

### 7.1 用户结果

危险 Tool 请求必须经过精确授权；修改已批准参数会使批准失效；shell/code 只在隔离 runner 中执行；
单用户服务可以通过认证和 HTTPS 安全访问，并且能从备份恢复。

### 7.2 三道门

1. **权限门**：Grant 表达主体、动作、资源和约束；Policy 默认拒绝；Approval 绑定 Run、Tool call、
   规范化参数 hash、有效期和一次性 nonce；
2. **隔离门**：runner 无特权、只读 rootfs、每 Run workspace、资源与输出受限、默认断网，不挂密钥、
   主数据库、宿主根目录或 Docker socket；
3. **部署门**：CLI/API 共用 application command；加入认证、SSE 续接、HTTPS、备份和恢复演练。

登录只确认用户身份，不自动授予 Tool 权限；sandbox 也不能代替 Policy 检查。runner 不可用时不得
回退到 host subprocess。

### 7.3 P3 明确不做

Web UI、MCP、Skill、Memory、浏览器、任意通用联网、多用户、组织 RBAC、插件市场、PostgreSQL、
Redis、queue 和多 worker。

### 7.4 P3 退出证据

- 十个固定 workspace 任务至少八个无需修改代码完成；
- 模型完成、workspace 写提交和等待批准三个边界的中断恢复符合契约；
- workspace 逃逸、Prompt injection 提权、批准参数篡改和 host shell 测试全部阻断；
- 每个 Run 可导出 Event/trace，`UNKNOWN` 明确可见；
- runner 读不到 Provider key、宿主根目录、主数据库和 Docker socket；
- Docker Compose 可在干净 Linux 环境部署，并从 SQLite + Artifact 备份恢复；
- `agent.bearguin.cn` 只通过 HTTPS 和认证访问，内部端口不直接暴露公网；
- 新开发者只靠仓库文档即可解释核心边界、失败方式和验证命令。

## 8. P4：日常使用

**状态：未开始。**

先接入一个版本化只读 Skill，证明说明文件不能扩大权限；再接入一个受控只读 MCP Tool，证明外部
工具仍经过相同的 Policy、Event、timeout 和输出限制。之后再增加 Web UI、带来源且可删除的
Memory、受控联网和 Provider 配置体验。

验收重点：

- Skill 不修改 Runtime 内核，也不能授予权限；
- MCP Tool 和内置 Tool 运行同一组权限、故障和记录测试；
- Memory 显示来源、置信度和有效期，用户可以删除；
- 上下文压缩后仍能通过 Event 或 Artifact 回到原始证据；
- Web 和 CLI 操作同一个 Run，没有两套业务逻辑。

## 9. P5：持续评测

**状态：未开始。**

P5 把 P1 的任务、P2 的恢复演练和 P3 的安全演练接入统一追踪，比较模型、Prompt、Skill 和 Tool
版本带来的答案、执行路径、成本和延迟变化。它负责平台化早期证据，不是第一次开始评测。

费用估算不回填到 P1 的 `config.json`。P5 在开始相应 Feature 前设计独立、版本化的
`PricingCatalog` 和费用策略：实际 token usage 继续来自 Provider，估算值必须记录价格来源、生效时间
和版本；没有可用价格时显示为未定价，而不是把 `0` 表述为真实零费用。只有无人值守执行、多模型
比较或明确金额上限证明需求后，才加入按金额阻止后续 Activity 的策略。P1 的真实模型 gate 继续使用
与用户配置分离的固定 pricing snapshot 和 suite cost cap。

关闭 P5 时，固定评测可在 CI/nightly 复现；修改模型或 Tool schema 后能看到答案和 trace 回归；
文档中的每项核心承诺都能链接到代码或测试证据。

## 10. P6+：只有需求证明后再做

- Child Run 形式的多个 Agent；
- schedule、webhook 和长 timer；
- 浏览器和电脑控制；
- 向量检索；
- 消息渠道；
- PostgreSQL、多 worker、queue 和 lease；
- Temporal 或其他 durable workflow engine；
- 多用户和租户隔离。

进入任一项前都要给出触发证据，例如 SQLite 写竞争达到阈值或任务需要跨天 timer，而不是因为
参考项目已经支持。

## 11. Feature Backlog

Feature ID 在全项目稳定。未创建 Spec 的名称只表示计划范围；开始前必须创建 Spec 并声明 milestone。
移动阶段时不重编号。

### P1

1. [F-0001：内部 ID、Message 和 Error](../specs/F-0001-domain-ids-messages-errors.md) — implemented
2. [F-0002：Run/Activity 状态和预算](../specs/F-0002-run-reducer-activity-lifecycle-budgets.md) — implemented
3. [F-0003：Event store、SQLite、projection 和 migration](../specs/F-0003-event-store-sqlite-projections.md) — implemented
4. [F-0006：Tool 接口、Registry、executor 和固定 Policy](../specs/F-0006-tool-registry-executor-policy.md) — implemented
5. [F-0007：workspace 边界和只读工具](../specs/F-0007-workspace-read-tools.md) — implemented
6. [F-0008：原子写和 Artifact](../specs/F-0008-atomic-output-artifacts.md) — implemented
7. [F-0004：模型接口和首个真实 adapter](../specs/F-0004-model-provider-first-adapter.md) — implemented
8. [F-0016：ContextBuilder、有界 Loop、Agent 配置和评测任务](../specs/F-0016-bounded-context-agent-loop.md) — implemented
9. [F-0005：`run/inspect/events` CLI](../specs/F-0005-run-inspect-events-cli.md) — implemented
10. [F-0015：本地 Starlight 文档站](../specs/F-0015-local-starlight-docs-site.md) — implemented
11. [F-0017：用户配置模型服务和 P1 live-model gate](../specs/F-0017-configurable-model-providers-live-gate.md) — implemented

### P2

1. F-0009：Checkpoint、重放和启动恢复
2. F-0010：pause/cancel/retry、幂等、Receipt 和 `UNKNOWN`

### P3

1. F-0011：Grant、Policy 和持久 Approval
2. F-0012：sandbox runner 和 code Tool
3. F-0013：HTTP API、SSE 和认证
4. F-0014：Compose、加固、备份和恢复

如果一个条目在写 Spec 时仍无法独立验收，保留现有 ID 的核心范围，并用新的全局 ID 拆出后续
Feature。一个 Plan 不得同时实现整个阶段。

## 12. 维护这份路线图

- 每个 Feature 完成时，同步工程 `docs/`、相关学习页、开发者导读和当前状态；
- 每个阶段完成时，再同步本 Roadmap、学习地图、架构总结和阶段结果；
- 外部项目只能提供概念和方案对照，不能建立 BearAgent 当前能力；
- 同时最多一个 active 主 Plan；
- 阶段只由可复现退出证据关闭，不按主观百分比关闭。
