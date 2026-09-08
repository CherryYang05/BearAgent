---
title: "Plan: Event-only replay and explicit startup inspection"
status: active
plan_id: PLAN-F-0021
related_spec: F-0021
created: 2026-09-08
last_updated: 2026-09-09
---

# PLAN-F-0021：先重建一个 Run，再检查尚未结束的执行

关联 [F-0021](../specs/F-0021-event-replay-startup-check.md) 与
[ADR-0020](../adr/ADR-0020-event-replay-before-recovery.md)。2026-09-08 获准开始实现，本 Plan 为唯一 active Plan。

## 已核对的起点

- P1 收口 PR #25 已合入 main，annotated tag `v0.1.0` 指向 `499e244`，远程 tag 已核对。
- 工作分支为 `codex/F-0021-event-replay-startup-check`，一个分支只承载 F-0021。
- P1 507 个测试、Ruff、Pyright、锁文件、governance 和站点构建通过；收口提交的
  [main CI](https://github.com/CherryYang05/BearAgent/actions/runs/34217884668) 与
  [文档部署](https://github.com/CherryYang05/BearAgent/actions/runs/34217884676) 均成功，公网状态页
  返回 200 并包含收口日期。这些不是 F-0021 验收结果。
- `RunQueryService` 与 SQLite 的 Event 读取都依赖 projection。临时实验删除 projection 行后仍有
  9 个 Event，但两个读取入口均返回 `persistence_error`；实验只使用测试 fixture，已清理。
- `reduce_events()` 校验完整历史，`validate_event_history()` 约束 v2/v3/v4 Tool 请求一致性；应复用。
- 启动设计时尚无 replay/check；以下切片记录本次新增行为。已有 Event schema 与 SQL migration 保持不变。

## 开始实现前

- [x] 接受 F-0021 的只读重建与显式检查范围、命令、上限和退出码。
- [x] 接受 ADR-0020，明确不自动修复 projection、不创建 Attempt 或恢复决定。
- [x] 把 Spec 改为 accepted、ADR 改为 accepted、本 Plan 改为唯一 active Plan。

## 第 1 步：projection 不可用时仍能重建一个 Run

- 状态：本地实现与验证完成。
- 交付：独立只读 source、冻结快照类型、application replay service、版本化 state hash。
- 连接：SQLite/内存 adapter -> EventReplaySource -> existing Reducer -> 重建结果。
- 证据：共用 contract；v1-v4、缺失/损坏 projection、坏 Event、数量/字节边界和状态 hash 固定样例。
- 验证：新增 replay 契约与集成测试、已有 EventStore contract、Reducer 与 schema tests、Pyright。
- 回退：不接 CLI 即可停用新增 reader；无数据迁移或写回。

## 第 2 步：从 Event 发现 Run，报告未结束和异常项

- 状态：本地实现与验证完成。
- 交付：有界枚举、显式游标、逐 Run 快照、非终态边界及 projection 对照；坏历史返回安全错误项。
- 证据：错误终态 projection 不漏检、全终态页仍能翻页、并发追加不混合快照、锁等待与取消资源释放。
- 验证：内存/SQLite 共用扫描契约与双连接 integration tests；记录规模、耗时、环境与资源上限。
- 回退：停用扫描 service，不改已有单 Run 读写命令。

## 第 3 步：用户可以只读 replay/check，并看清它没有继续执行

- 状态：本地实现与验证完成。
- 交付：bootstrap 组装、human/JSON 输出、命令帮助与退出码；默认数据库路径沿用 P1。
- 证据：没有 config/key 也能读取；不存在数据库不创建文件；K1-K6 之后重建最后事实且零额外模型、
  Tool、replace；旧 CLI/JSON 保持兼容，新命令名可作为转义后的普通目标。
- 验证：CLI integration、版本化 schema、hard-process suite、完整 pytest/Ruff/Pyright/governance、
  文档链接、站点 build 和 wheel smoke；远程 Windows/Linux CI。
- 回退：移除新增 CLI 注册；保留全部历史数据及既有命令。

## 文档和阶段边界

Spec 所列权威 docs、初学者、开发者和公开状态表面已同步。页面区分 P1 的 main/tag 基线与 F-0021
工作分支，不把只读检查写成恢复执行。Spec 和 ADR 均为 accepted；Plan 保持唯一 active，以准确
保留实现提交和远程 CI 的剩余项。F-0022 仍未接受，不在本分支实施。

## 本地验证（2026-09-08）

- `uv run pytest --basetemp=.pytest-tmp-f21full -o cache_dir=.pytest-state-f21full -q`：555 passed；
  包含内存/SQLite 共用契约、v1-v4、固定 hash、projection 故障、Event 缺口、Tool 请求不一致、
  分页、快照并发、锁等待、查询超时、取消释放与超限预检。
- K1-K6 原有 hard-process 测试增加新进程 replay/check：最后提交边界一致，数据库事实、模型调用
  记录和 workspace 文件保持不变；K5 仍停在 rollback 前 sequence 2。
- CLI 测试覆盖无 config/profile、无凭据、缺库不创建、安全 human/JSON、退出码及保留词转义。
- `uv run python scripts/benchmark_event_replay.py`：100/1,000 条分别约 0.020/0.467 秒；10,000 条
  触发 30 秒期限。输入上限不承诺完成时延，长历史 Reducer 成本仍需后续优化或 Checkpoint 设计。
  数据与环境见 [F-0021 benchmark v1](../evidence/F-0021-replay-benchmark-v1.json)。这是合成数据，
  没有访问用户数据库、workspace 或真实 Provider。

- `uv run ruff check .`、`uv run ruff format --check .`、`uv run pyright`、`uv lock --check`：通过。
- `uv run python scripts/check_governance.py`：16 Specs、15 Plans、20 ADRs 通过；唯一 active Plan 为本计划。
- `uv run python scripts/check_docs.py`：155 个 Markdown 文件的本地链接通过。
- `npm run build --prefix=site`：48 页、Pagefind、sitemap 成功；仍有既有的大 bundle 提示。
- `uv build --offline`：sdist 与 wheel 构建通过。wheel 用 `uv pip install --no-cache --no-deps --target`
  安装到独立临时 target，复用项目依赖，并断言 `bearagent.__file__` 来自安装产物；
  `scripts/smoke_wheel_cli.py` 的 Run/inspect/events/replay/check 全部通过。
- schema 与 HEAD 比较：仅新增 7 个 domain 查询类型、3 个 CLI 结果类型及 `query_timeout` 枚举值；
  既有类型其余结构不变，SQL migration 未修改。`git diff --check` 通过。

## 待补齐的发布证据

- [ ] 提交本次实现，在 `implemented_in` 记录对应不可变提交或 PR。
- [ ] 推送实现后核对相同提交的 Windows/Linux CI 与站点构建结果。
- [ ] 上述证据齐备后，将 Spec 标为 implemented、Plan 标为 completed，并同步索引和公开状态。

2026-09-09 项目所有者授权收口并推送本 Feature。本次先提交实现并创建 PR 验证跨平台 CI，再用实际
提交与检查结果关闭 Spec/Plan；已有设计提交为 `7a5a468`。Feature 收口不代表合入 main 或发布新 tag。
