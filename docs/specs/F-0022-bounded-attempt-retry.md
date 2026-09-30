---
title: "Feature: record every Attempt and bound safe retries"
status: implemented
spec_id: F-0022
milestone: P2
change_level: S2
owner: CherryYang05
created: 2026-09-13
last_updated: 2026-09-30
implemented_in: "PR #29 / commit 40d26a5fb3b5d6fe48eef612d685eba2f70f467d"
related_adrs: [ADR-0002, ADR-0003, ADR-0009, ADR-0013, ADR-0016, ADR-0020, ADR-0021]
---

# F-0022：每次执行尝试都有记录，只有证据允许时才有界重试

## 1. 从一次读取超时开始

假设模型要求读取 `docs/architecture/overview.md`，文件工具第一次超时、第二次成功。用户应该看到
一个读取 Activity 和两个 Attempt：Activity 是同一个逻辑动作，Attempt 是一次进入执行流程的尝试。
第一次失败不能被第二次成功覆盖，工具调用预算也必须记两次。

2026-09-13 核对了 main `28fc873`：[F-0021 PR #26](https://github.com/CherryYang05/BearAgent/pull/26)
已合并，Spec 为 implemented，Plan 为 completed，没有 active Plan。当时基线代码的差距是（下面描述实现前状态）：

- `application/agent_loop.py` 在模型失败后保存 ModelCallFailed 并结束 Run；Tool 失败通常交回模型，
  模型仍可提出下一次动作。当前没有 Attempt 或 Runtime retry。
- `runtime/reducer.py` 在 ModelCallRequested / ToolCallRequested 时计算调用次数；直接在 adapter
  外加重试循环，会让实际调用次数与预算分叉。
- `runtime/tool_executor.py` 已统一 prepare、Policy、timeout 和结果校验，但 Started Event 在调用
  Executor 前保存，无法区分“进入检查流程”和“通过 Policy 后开始外部执行”。
- 三种模型 adapter 均禁用 SDK 自动重试。`ErrorInfo.retryable` 与 `ToolRetrySafety` 只是提示。
- F-0021 可以重建最后提交状态；它不能授权重做，也不会扫描后自动续跑。

现有 AgentLoop、预算、Reducer 和 append 失败边界共 62 个定向测试通过。这是设计基线，不能当作
本 Feature 的验收结果。项目所有者于 2026-09-13 接受设计并授权开始实现；关联 [ADR-0021](../adr/ADR-0021-attempt-ledger-before-retry.md)
和 [PLAN-F-0022](../plans/PLAN-F-0022-bounded-attempt-retry.md)。

## 2. 本次交付与后续边界

本次交付模型和 Tool 的 Attempt 事实、确定性的失败分类与恢复规则，以及当前进程内的串行有界
retry。每个失败 Attempt 都留下“重试、交回模型或停止”的 RecoveryDecision，再按决定继续。
新增只读查询，让用户能查看尝试次数、失败原因、延迟、预算和决定依据。

自动重试只开放给具有可信无副作用语义的只读 Tool，以及有明确证据表明尚未提交到服务端的短暂
模型连接失败。模型请求的重试不改 Provider、模型、Prompt、参数或工具集合。

幂等写入、Receipt、reconcile、正式 `UNKNOWN` 状态与人工处置留给 F-0023；重启续跑和
pause/resume/cancel/retry 命令、完整 kill-point suite 与策略比较留给 F-0024。本次提供自身新增
边界的中断测试，不借此宣称 P2 已完成。Checkpoint、P3 授权/隔离和新生产依赖不在范围内。

## 3. 用户会看到什么

### 3.1 正常执行与显式启用

普通 `bearagent run "..."` 仍使用默认配置位置。新 Run 保存 Event schema v5，无论是否开启重试
都记录 Attempt。现有 RunProfile v1/v2 保持可读，并映射成每个 Activity 最多 1 次尝试。

增加 RunProfile v3，在 v2 的 Provider 选择和 Agent 设置之外增加 `retry_policy`。建议值如下：

```json
{
  "max_attempts": 3,
  "initial_backoff_ms": 250,
  "max_backoff_ms": 2000
}
```

这是 v3 中的字段示例，不是完整 profile。`max_attempts` 包含第一次尝试，默认 1，上限 3；延迟
默认 250/2000 ms，满足 `1 <= initial_backoff_ms <= max_backoff_ms <= 5000`。每个字段严格校验，
不接受无限重试、负数或由模型指定的策略。`init` 默认仍生成单次尝试配置，不改写现有用户文件。
配置经过可信入口验证后写入 RunCreated，规则版本固定为 `bounded-retry-v1`。

### 3.2 一次失败怎样处理

| 已提交的失败及执行证据 | 本次规则 |
|---|---|
| 注册为 READ_ONLY 的 Tool 超时；前一次协程已退出；当前 Policy 仍允许 | 次数、共同 deadline 与 Run budget 均允许时重试 |
| 模型连接短暂失败，adapter 明确证明模型请求未提交 | 在同样上限内重试；失败用量可记为已知零 |
| 模型超时、部分流、用量不明，或只有 429/5xx/连接异常这一粗粒度码 | 停止自动重发；不得把缺失 usage 当作已知零 |
| 输入无效、路径或权限拒绝、永久故障 | 不自动重试；无副作用的普通 Tool 失败可按原语义交回模型 |
| 只读 Tool 的安全 retry 用完 | 形成 Activity 失败，最终错误交回模型；新的模型动作仍受 Run budget 约束 |
| 写入已进入 adapter，随后超时、异常或结果证据无法完整保存 | 停止整个 Run，不再调度模型或 Tool；明确显示副作用结果不明 |
| Event append 失败、取消或进程中断 | 停在最后 committed fact，不补造结束或成功，不创建下一次尝试 |

模型返回新的 ToolCallId 表示新 Activity；不能把它伪装成旧 Activity 的第二个 Attempt。普通只读
失败交回模型后不承诺阻断一切重复提议，Run hard budget 仍兜底。写入结果不明时必须停止整个调度链，
防止模型通过换一个 ID 再提写入绕过停止决定。

### 3.3 查询

新增 `bearagent run attempts RUN_ID`，支持 human/JSON 和有界 sequence 游标分页。默认每页 100 项，
上限 1000；输出 ActivityId、AttemptId、序号、状态、失败类别、执行边界、关联决定和已知用量。
不输出目标、请求正文、规范化参数、ToolResult 或原始异常；完整事实仍由显式 `events --json` 读取。

旧 v1-v4 Run 返回“历史未记录 Attempt”，不制造 AttemptId 或推算一次真实调用。旧 inspect/events
结果保持兼容；新增字段放入版本化的新查询契约。replay/check 支持 v5，但保持只读且不获准执行。
缺库不创建数据库，查询不读取 config/profile/key。`attempts` 作为普通目标时沿用 `run -- OBJECTIVE`。

## 4. 谁负责判断，谁负责执行

Runtime 的纯规则接收 BearAgent 类型：失败证据、注册契约、历史 Attempt、预算、期限和候选延迟；
返回允许的下一步及固定理由码。它不读时钟、不随机采样、不访问数据库，也不从错误文本猜根因。

Application 协调 append、等待与执行，时钟、等待器和随机源可替换以便确定性测试。ToolExecutor
继续唯一负责 Registry -> prepare -> Policy -> bounded execute；增加受控的执行前记录边界，把
通过检查的规范化请求和 Policy 结果保存后才调用 Tool adapter。保存失败必须透传并阻止调用，
不能被包装成普通 Tool 错误后继续。每次 retry 都重新 prepare 和检查 Policy，规范化参数或注册
contract 与首次快照不一致时停止该 Activity，不执行变更后的请求。

ModelProvider adapter 只翻译传输事实，不决定 retry。新增模型失败证据区分明确未提交与提交结果
不明，并区分已知用量与未知用量；默认是未知。不得仅凭 `PROVIDER_UNAVAILABLE` 推断未提交，
因为当前这个码还涵盖普通 HTTP 错误和服务端 5xx。三种协议使用同一行为契约，SDK/transport retry
保持禁用，不把 SDK 异常或响应类型送入核心。

## 5. 状态、Event 和预算

### 5.1 Activity 与 Attempt 的边界

同一个 Activity 只请求一次、只终结一次。每个 Attempt 具有独立 UUID4、从 1 连续增长的序号、
父 ActivityId、请求引用、共同 deadline、可空开始/完成时间和结果证据。未通过 prepare/Policy
的尝试可以失败但没有 Started；“请求了一次执行”不等于“外部动作一定发生”。

新增 `AttemptRequested`、`AttemptStarted`、`AttemptSucceeded`、`AttemptFailed` 与
`RecoveryDecisionRecorded`。模型/Tool 原有的逻辑 Activity Event 在 v5 连接这些事实：

```text
Activity requested/started
  -> AttemptRequested #1 -> 检查 -> AttemptStarted #1 -> 外部执行
  -> AttemptFailed #1 -> RecoveryDecisionRecorded(RETRY)
  -> 有界等待 -> 再检查预算 -> AttemptRequested #2 -> 重新检查 -> AttemptStarted #2
  -> AttemptSucceeded #2 -> Activity completed
```

Decision 引用失败 Event、Activity、Attempt、策略版本、契约 hash、截止 sequence、理由码及实际
等待时间。`RETRY` 决定只能连接一个新的 Attempt；`RETURN_TO_MODEL` 和 `STOP_RUN` 连接逻辑终态。
Reducer 拒绝跨 Run 引用、跳号、并发 Attempt、失败前决定、成功后重试和重复消费同一决定。
Decision 仍不是权限凭证；执行前必须重新通过 Policy。成功路径不伪造恢复决定。

ContextBuilder 只把最终 Activity 结果交给模型。中间失败 Attempt 不重复生成 ToolResult Message，
失败模型流中的 ToolCall 不执行；最终模型结果的 ToolCall ID 与对应结果仍一一匹配。

### 5.2 使用同一份预算

v5 在 AttemptRequested 时增加模型或 Tool 调用次数；逻辑 Activity requested 不再重复记账。
拒绝进入 adapter 的尝试也消耗一次请求额度，和现有防止无效请求无限循环的边界一致。已知
token/cost 在 Attempt terminal 时记一次，逻辑 Activity terminal 只汇总并校验，不再次累加。
旧 v1-v4 仍按原规则重建，不能换用新计数语义。

一个 Activity 共用首次请求时确定的总 deadline：以 `max_attempts * 单次 timeout + 各次退避上限之和`
作为最长执行窗口，再受 Run 剩余总时间约束。单次 timeout 使用首次 ModelRequest/ToolSpec 的值；
每次实际调用取单次 timeout 与剩余窗口的较小者。这样首次超时后仍可能有时间重试，但后续尝试
不能刷新整个窗口。max_attempts=1 时仍只有原来的单次 timeout。采用指数 backoff 与 full jitter，
范围为 `[0, min(max_backoff_ms, initial_backoff_ms * 2^(n-1))]`，n 是重试序号。
实际延迟写进决定；replay 不重新抽样或等待。等待前后及实际 dispatch 前都重新检查预算和期限。

未知模型用量显式显示为未知，已记录总量只是已知部分，不宣称它限制了未报告的远端账单。
因此提交结果或 usage 不明的失败本次直接停止，不消耗新的模型 Attempt。普通 `unpriced` 的
既有限制继续明示；不得因价格为零而声称调用免费。

### 5.3 兼容和存储

新写入统一使用 schema v5；一个 Run 内不混用新旧执行语义。v1-v4 Event、其持久 JSON fixture、
fingerprint、固定 state hash 和计数规则保持原义。公开 schema 可增加新类型、联合分支与稳定错误码；
旧 RunState 不能增加默认字段，也不能改变已有字段的含义。增加的恢复契约必须进入新的版本化 contract identity；不能给旧
ToolSpec/fingerprint 补字段后重新算出一个不同的历史 hash。

SQLite 增加 `0002` migration 和派生的 Attempt/Decision 查询数据，以及 Run/Activity 必要的版本
信息；不修改 `0001_initial.sql` 或历史 Event。append、Reducer 和各 projection 在同一个 transaction
内提交。旧 Run 不回填不存在的 Attempt 事实；migration 失败全部回滚，ledger checksum 继续校验。

F-0021 state hash v1 的输入是完整旧 RunState。新 Attempt 状态必须使用 state format v2，不能在
v1 哈希输入里悄悄加默认字段。旧历史保留 v1 固定 hash，新历史使用 v2；两种格式分别比较，不能
跨版本把 hash 不同解释为损坏。projection 缺失时 v5 仍能从 Event 完整重建。

## 6. 失败、恢复和安全

失败分类至少包含 `INVALID_INPUT`、`TRANSIENT_INFRASTRUCTURE`、`PERMANENT_FAILURE`、
`PERMISSION_DENIED` 和 `EFFECT_INDETERMINATE`。它描述处理依据，不声称诊断出了根因。
`ToolSideEffect` 描述影响范围；新的版本化恢复声明区分 `READ_ONLY`、`IDEMPOTENT`、
`RECONCILABLE` 和 `NON_IDEMPOTENT`。后面三类本次均不启用写入 retry，也不因声明本身授予权限。
workspace.write 在核对机制交付前按不可自动重做处理，不能提前宣称可 reconcile。

写入进入 adapter 后的失败默认归为 EFFECT_INDETERMINATE。若仍能提交 Event，则保存停止决定、
逻辑失败与 RunFailed，同时明确错误码 `effect_indeterminate`。这表示 Runtime 停止，不表示写入没
发生，也不是 F-0023 的正式 UNKNOWN 状态。若结果或决定保存失败，则保持最后非终态事实。

取消不转成自动 retry。退避中取消立即停止调度；前一 Tool 协程未退出时不得启动下一 Attempt。
协作式 timeout 不承诺撤销系统调用；不引入 host shell 或任意强杀。缺失 terminal Event 一律不能
推断为“没执行”。重启后的 replay/check/attempts 只查询，旧 Run 和中断 Run 均不自动续跑。

每条 Event 继续受既有字节、节点数与深度上限约束。新增记录不会复制完整请求到每个 Attempt；
通过同一 Run 的 Event 引用校验原始请求，Started 保存必要的规范化执行证据。读历史继续受 F-0021
数量/字节/期限约束，超限安全失败，不扩大上限来掩盖新增记录成本。持久化或内部错误不能重试。
诊断沿用固定字段白名单，不把请求、路径、密钥、结果、原始异常或新恢复 payload 送入日志。

## 7. 启用、迁移和回退

接受设计后先实现新旧 Event 与 migration 的契约测试，再连接 Fake 执行链，最后接入生产组装和
CLI。升级前停止 writer，并用 SQLite backup API 或关闭连接后的完整备份保存一致数据库；测试只
操作临时 fixture。迁移需要的磁盘/锁失败必须安全退出，不能留下半迁移 schema。

禁用 retry 可将新配置的 max_attempts 改为 1，但仍使用支持 v5/migration 2 的 reader。降级到旧
二进制前必须恢复升级前备份或使用新数据库；旧版本不支持读写 v5，禁止在新库上继续写入、删除
新 Event 或改写其版本号。备份恢复会放弃备份后的数据库事实，必须保留新库副本供检查。

## 8. 验收标准

| AC | 可判断的结果 | 验证入口 |
|---|---|---|
| AC-1 | 一个只读 Activity 首次失败、第二次成功；两个 Attempt、一次最终结果、调用预算为 2 | Fake + 真 ToolExecutor + 内存/SQLite 集成 |
| AC-2 | 失败分类与可信副作用/提交证据共同决定下一步，单独 retryable=true 无效 | 纯规则表驱动与伪造输出安全测试 |
| AC-3 | 次数、token、cost、总时间、共同 deadline 与 backoff 任一耗尽都阻止下一次执行 | 固定时钟/随机源/等待器；边界前后各一例 |
| AC-4 | 每次 Tool retry 重新 prepare/Policy；参数或契约漂移、拒绝、Started append 失败时零额外调用 | Executor 安全与 append 故障注入 |
| AC-5 | 模型只有明确未提交的短暂失败可重试；三协议无隐藏 retry；部分流/未知 usage 不重发 | 模型 port 共用契约、模拟 HTTP transport、零真实 Provider |
| AC-6 | 写入后报错只执行一次，Run 停止；后续模型和排队 Tool 都不执行 | 真实临时 workspace.write + 故障 wrapper；模型提出重复写入的 canary |
| AC-7 | terminal/Decision/下一 Started 之间中断后只查询，外部执行次数不增加 | 独立子进程 kill point、SQLite 重开、replay/check/attempts |
| AC-8 | v1-v4 固定 hash/JSON/预算不变；v5 两存储状态等价；非法关联和混合历史被拒绝 | schema、Reducer、EventStore/replay contract |
| AC-9 | migration 与 projection 事务失败完整回滚；新库不会被旧 writer 静默写入 | SQLite migration/rollback 与旧 reader 拒绝测试 |
| AC-10 | 新查询有界、分页明确、输出安全且不需凭据；原 CLI 兼容 | CLI/schema、缺库、敏感 canary、wheel smoke |
| AC-11 | Windows/Linux CI、完整离线套件、governance、文档和站点检查通过 | completed Plan 记录实际命令；不可用历史 62 tests 代替 |

测试报告记录故障位置、预期真值、输入 hash、规则版本、实际次数和额外用量。实验真值只供断言，
不输入恢复规则；本次记录可供 F-0024 扩展，不搭建候选算法或完整实验平台。

## 9. 文档影响

本次实现已同步以下表面；完整验证结果与发布状态记录在 Plan。

| 表面 | 更新路径，或 N/A 与原因 |
|---|---|
| 权威 docs | 本 Spec、ADR-0021、PLAN-F-0022、三个索引及 roadmap；已更新 architecture/overview 的状态、预算和版本边界 |
| 初学者 | 已更新 `learn/recovery-authority-isolation.md`、`learn/runtime-state-and-budgets.md`、`learn/index.md` 和 `guides/cli.md`，用一次只读失败示例解释 Attempt |
| 开发者 | 已更新 `development/agent-loop.md`、`development/run-reducer-and-budgets.md`、`development/tool-execution-boundary.md`、`development/model-provider.md`、`development/sqlite-event-store.md` 与开发者索引、architecture/index.md、architecture/runtime-flow.md |
| 公开状态 | 已更新 `project/status.md` 和 `project/milestones.md`；仅声称进程内安全 retry，仍标明 F-0023/F-0024 未交付；README 已更新能力表和当前 P2 范围；新 profile 与 attempts 的详细选项由 CLI 手册承接 |
| 生成参考 | 已更新 domain/CLI JSON schema，检查旧格式固定样例；已更新 runtime configuration schema 与完整 v3 profile 示例 |

## 10. 已接受的关键取舍

默认单次尝试，显式最多 3 次；保留独立单次 timeout 与首次请求起固定的总 deadline。未知模型用量
停止重发，写入结果不明先停止 Run，核对/UNKNOWN 处置留给 F-0023。2026-09-13 已接受；
ADR 为 accepted；Spec/Plan 状态分别记录实现与验证进度，P2 尚未关闭。

## 11. 实现与审查记录

实现使用 domain/attempts.py、runtime/attempts.py、runtime/attempt_reducer.py 与
application/attempt_execution.py，继续复用 ToolExecutor 和 ModelProvider port。
额外开发者页为 site/src/content/docs/zh-cn/development/bounded-attempt-retry.md，并接入导航。

2026-09-30 审查修正三类问题：传输读写失败不能被异常链中更早的连接失败误判为未提交；
真实 SDK transport 测试预留首次资源加载时间，避免一秒 fixture 干扰提交证据验证；未来 migration
测试使用版本 3，避免与本次新增版本 2 冲突。新增六个三协议读写错误链回归用例。
生成 schema 的扩展与旧持久 fixture/hash 的不变性分别验证，不能声称所有新旧参考 schema 字节相同。
