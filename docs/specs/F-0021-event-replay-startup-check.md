---
title: "Feature: reconstruct Run state from Events and inspect unfinished Runs"
status: implemented
spec_id: F-0021
milestone: P2
change_level: S2
owner: CherryYang05
created: 2026-09-08
last_updated: 2026-09-09
implemented_in: "PR #26 / commit c1a94da8bc5c90dc49edc07184d7ee076a63b419"
related_adrs: [ADR-0002, ADR-0003, ADR-0009, ADR-0016, ADR-0020]
---

# F-0021：不用 projection，也能重建 Run 并检查未结束的执行

## 1. 从一次中断后的查询开始

P1 的 `v0.1.0` 已固定在 main 提交 `499e244`。用户启动 P2，首先需要知道数据库中保存了什么，
再决定后续能否恢复。项目所有者于 2026-09-08 授权实现，2026-09-09 授权收口并推送。
实现提交 `c1a94da8bc5c90dc49edc07184d7ee076a63b419` 已通过 [Windows/Linux 与站点 CI](https://github.com/CherryYang05/BearAgent/actions/runs/34251928326)，
本 Feature 在 [PR #26](https://github.com/CherryYang05/BearAgent/pull/26) 完成收口。合入 main 的状态以 PR 为准。

2026-09-08 的临时 SQLite 实验写入 `successful_run_events()` 的 9 条 Event，再删除 Run/Activity
projection 行。Event 数量仍为 9，Reducer 的参考结果为 `succeeded`、sequence 9；但现有 `inspect`
与 `list_events` 都抛出 `EventStoreCorruptionError / persistence_error`。临时数据已经清理，没有访问
用户数据库或模型凭据。

原因在于 `RunQueryService._require_run()` 首先读取 projection，而 SQLite 的 `_list_events_sync()`
也先校验 projection。`reduce_events()` 已有状态与跨 Event 请求一致性校验，但没有一个独立读取
持久 Event、固定读取边界并把结果交给用户的入口。P1 的 K1-K6 只证明最后提交事实可见。

## 2. 本 Feature 交付什么

1. 从完整、受限的 Event 历史重建一个 Run，返回状态、最后 sequence、版本化 state hash 与 projection 对照结果。
2. 从 Event 中发现 Run，检查并列出非终态 Run；projection 缺失、损坏或错误标为终态都不能让它漏检。
3. 用同一契约约束内存与 SQLite adapter；复用现有 Reducer，不实现第二套状态机。

本次不追加恢复 Event，不写回 projection，不重新调用模型或 Tool，不读取 workspace 核对文件。
Attempt、retry、Receipt、reconcile、`UNKNOWN` 处置和控制命令分别留给 F-0022 至 F-0024。
Checkpoint 暂不交付：先记录代表性历史的重放成本，再决定是否增加可删除缓存。

## 3. 用户会看到什么

F-0021 已实现以下只读接口；P1 的 `v0.1.0` 不包含它们：

```console
bearagent run replay RUN_ID
bearagent run replay RUN_ID --json
bearagent run check
```

`replay` 只读取指定 Run 的事实。完整历史可重建时，即使 projection 不可用，也返回 Event 推导的
状态摘要，并单独报告 `matched / missing / mismatch / unreadable`。它不把“对照失败”当作 Run 失败，
也不把缺失 terminal Event 的 Activity 改为成功或 `UNKNOWN`。

`check` 是显式的启动前检查，不自动附着到每次 `run`。它按有界页扫描 Event 中的 Run ID，显示非终态
Run、最后提交边界、projection 异常与单 Run 读取错误。仍在运行的进程也可能留下非终态，因此输出
只写“尚未结束”，不能据此断言进程已崩溃、无人执行或已获准重试。

两条命令沿用 `data/bearagent.db`，允许 `--database` 临时覆盖；不读取 config/profile，不创建数据库。
默认输出仅含 ID、状态、sequence、hash 和安全理由码，不打印目标、消息、Tool 参数或 payload。
`--json` 使用新增的版本化结果，不改已有 inspect/events JSON。新命令名与目标重名时，沿用
`bearagent run -- OBJECTIVE` 的转义路径并更新 help。

## 4. 模块怎样连接

新增只读 `EventReplaySource` port，返回 BearAgent 内部快照类型；不放宽 P1 EventStore 的 append、
get_run 或 list_events 语义。SQLite adapter 在一个读事务内捕获每个 Run 的 Event 前缀及 projection
对照资料，内存 adapter 提供同样的快照语义。application replay service 调用已有 Reducer，构造结果；
CLI 通过 bootstrap 组装，不在接口层读取 SQL 或直接导入模型/Tool adapter。

Run 枚举也从 Event 表出发。一次扫描返回有界页及下一页游标；UUID 排序只服务分页，不能解释为时间
或恢复顺序。跨页新建的 Run 留给后续扫描，不声称整库扫描是同一时刻的完整快照；每个 Run 报告必须
明确自己的最后 sequence。适配器内部负责连接、事务、锁等待和取消后的资源释放。

## 5. 状态、版本和持久化

- 已有 Run/Activity 状态和 Event schema v1-v4 保持不变；逐条执行 parser、Reducer 和历史一致性检查。
- 未知 schema、sequence 缺口、非法转换、跨 Run Event 或不一致 Tool 请求都拒绝生成完整状态结果。
- state hash 带 `state_format_version`，以固定 UTC 时间格式、排序键、UTF-8 紧凑 JSON 和 SHA-256
  计算。它标识重建状态，不是 Event 内容签名，也不证明来源可信或允许恢复。
- legacy Run 缺少 fingerprint 时保持缺失；已知历史 contract 与当前 contract 不同仍可只读重建，
  不用当前注册信息补写历史。
- 不增加 SQL migration，不修改 `0001_initial.sql`，不重写 Event、projection、Artifact 或用户文件。
  projection 行或表缺失时，专用读取入口仍须能校验 ledger 和 migration；Event 表或 migration
  损坏则安全失败。现有写入路径仍可以因 projection 损坏而拒绝追加。

## 6. 失败、资源和安全边界

上限为单 Run 10,000 条 Event、16 MiB 序列化历史；读取前检查数量/字节界限，读取过程中
继续累计校验，超过任一上限都报告 `query_limit_exceeded`，不返回被截断却标为完整的 RunState。
扫描默认每页 100 个 Run，上限 1,000；每个 Run 处理后释放历史，避免整页 payload 同时留在内存。
空页与带下一页游标的空结果必须可区分，因为当前页可能全是健康终态。

SQL 使用参数绑定和 50 ms busy timeout；每条命令的读取与计算共用 30 秒 deadline。
SQLite progress handler 可中断查询，Event 读取和 Reducer 在条目之间检查期限。协程取消会通知
工作线程并等待连接关闭。单个条目的解析不能被 Python 强行中断，输入大小上限同时约束这段工作。
损坏单 Run 可作为安全错误项返回，不能让扫描跳过异常后声称全部健康。

人类和 JSON 输出均区分“找到非终态或异常，需要查看”与“检查本身失败”；采用退出码 0 表示所查
范围正常，1 表示需人工查看的非终态/projection 异常，2 表示参数、历史或读取失败。存在多个结果时
取最高严重级别。退出码 0 也不代表可以自动恢复；检查输出不能成为 Tool 权限。

查询不产生新的模型请求、Tool 调用、Event 或文件副作用。SQLite 自身的锁及 WAL/SHM 管理不属于
应用事实写入，但也不能用测试中的“文件字节完全不变”代替零业务写入断言。诊断仅记录固定 envelope
和安全错误码，不记录历史内容、路径、原始异常或凭据。

## 7. 启用与回退

先接受 Spec 与 ADR，再交付只读 port/service，最后接入 CLI。旧数据库与旧命令继续可用；本 Feature
不自动运行数据修复。回退时移除新入口和专用 reader 即可，数据库和用户资料不需要回滚。
整个数据库文件或 Event 本身损坏不在可重建承诺内，不提供自动猜测、丢弃历史或隐藏修复。

## 8. 验收标准

以下标准已由本地验证和实现提交的 [跨平台 CI](https://github.com/CherryYang05/BearAgent/actions/runs/34251928326) 覆盖。
Windows 和 Ubuntu 各 555 个测试通过，Starlight 构建通过；完整命令与边界见 completed Plan。

| AC | 可判断的结果 | 验证范围 |
|---|---|---|
| AC-1 | 同一 v1-v4 历史在内存和 SQLite 得到同一 RunState、sequence 和 state hash | 共用 replay source 契约；现有 schema fixture |
| AC-2 | projection 行/表缺失、错误终态或字段损坏时仍按完整 Event 重建，并报告对照异常 | 临时 SQLite 集成测试；P1 9 Event 示例扩为回归 |
| AC-3 | 未知版本、缺口、跨 Run 和 Tool 请求不一致都拒绝完整结果 | 安全与 Reducer 历史校验回归 |
| AC-4 | 写入并发发生时，只返回单个已提交前缀，不混合两个读取时刻 | SQLite 双连接事务测试；未提交 Event 不可见 |
| AC-5 | check 不依赖 projection 枚举；分页、全终态页、错误项及游标行为明确 | 内存/SQLite 共用扫描测试与 CLI 退出码测试 |
| AC-6 | K1-K6 之后可重建最后提交状态，模型/Tool/replace 次数不增加 | 复用 hard-process fixture；零额外调用断言 |
| AC-7 | 大历史、超限、锁等待与取消有界；错误输出不泄漏内容 | 边界/资源/安全测试，记录重放时间和输入规模 |
| AC-8 | 旧命令与 JSON 保持兼容，新命令无需 config 或真实 Provider | CLI/schema/安装 wheel smoke；完整 Windows/Linux CI |

## 9. 文档影响

| 表面 | 更新路径或 N/A 原因 |
|---|---|
| 权威 docs | 本 Spec、ADR-0020、PLAN-F-0021、`docs/architecture/overview.md`、`docs/project/roadmap.md`；说明事实读取与执行边界 |
| 初学者 | 已更新 `site/src/content/docs/zh-cn/learn/durable-events.md`、`learn/index.md`、`guides/cli.md`；加入一个 projection 缺失实例，并同步 `learn/recovery-authority-isolation.md`、`start/what-is-bearagent.md` 的阶段边界 |
| 开发者 | 已更新 `site/src/content/docs/zh-cn/development/sqlite-event-store.md`、`development/index.md`；说明只读快照与共用契约 |
| 公开状态 | `project/status.md`、`project/milestones.md` 区分 P1 发布基线与 F-0021 分支上的只读命令 |
| 生成参考 | 已更新 domain/CLI schema 快照；只新增查询类型及 `query_timeout` 错误码，不改 Event payload 和 SQL migration |

## 10. 实现与规模证据

`tests/contract/test_event_replay_contract.py` 在内存和 SQLite 上运行相同历史与分页测试；
`tests/integration/test_event_replay.py` 覆盖损坏、并发、锁等待、大小预检、deadline 与取消；
`tests/integration/test_replay_cli.py` 检查命令、退出码、内容保护与无配置读取。
K1-K6 的原有 `tests/recovery/test_crash_observability.py` 增加独立进程 replay/check，比较查询前后的
数据库事实、模型调用记录与 workspace 文件；wheel smoke 同样新增两条命令。

[规模记录](../evidence/F-0021-replay-benchmark-v1.json)使用临时 SQLite 与合成模型 Activity 历史。
100 条约 0.020 秒，1,000 条约 0.467 秒，10,000 条在约 30 秒返回 `query_timeout`，没有完整状态结果。
这是每档一次的 Windows 样本，不能作为其他机器的性能保证。10,000 条是输入上限，不保证所有合法
历史能在期限内完成；当前 Reducer 的长历史成本仍是限制。Checkpoint 和 Reducer 性能优化留待单独
设计并验证状态等价，不为本 Feature 增加缓存或迁移。

16 MiB 指各条 Event 的 `model_dump_json()` UTF-8 字节之和；SQL 先检查存储字段大小，再逐条累计
标准序列化大小。state hash v1 对完整 RunState 加 `state_format_version: 1` 外壳，使用排序键、
紧凑 JSON、UTF-8、UTC 六位微秒与 `Z`、小写 UUID，再计算 SHA-256。它不包含原始 Event payload；
完整 RunState 和历史 fingerprint 仅供内部查询，CLI 只序列化内容受限的摘要。
