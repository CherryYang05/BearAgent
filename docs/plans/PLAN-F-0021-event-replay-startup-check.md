---
title: "Plan: Event-only replay and explicit startup inspection"
status: draft
plan_id: PLAN-F-0021
related_spec: F-0021
created: 2026-09-08
last_updated: 2026-09-08
---

# PLAN-F-0021：先重建一个 Run，再检查尚未结束的执行

关联 [F-0021](../specs/F-0021-event-replay-startup-check.md) 与
[ADR-0020](../adr/ADR-0020-event-replay-before-recovery.md)。本 Plan 是启动草案，不是 active Plan。

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
- 没有修改生产代码、Event schema 或 SQL。当前没有任何 replay/check 命令可供使用。

## 开始实现前

- [ ] 接受 F-0021 的只读重建与显式检查范围、命令、上限和退出码。
- [ ] 接受 ADR-0020，明确不自动修复 projection、不创建 Attempt 或恢复决定。
- [ ] 把 Spec 改为 accepted、ADR 改为 accepted、本 Plan 改为唯一 active Plan。

## 第 1 步：projection 不可用时仍能重建一个 Run

- 状态：pending。
- 交付：独立只读 source、冻结快照类型、application replay service、版本化 state hash。
- 连接：SQLite/内存 adapter -> EventReplaySource -> existing Reducer -> 重建结果。
- 证据：共用 contract；v1-v4、缺失/损坏 projection、坏 Event、数量/字节边界和状态 hash 固定样例。
- 验证：新增 replay 契约与集成测试、已有 EventStore contract、Reducer 与 schema tests、Pyright。
- 回退：不接 CLI 即可停用新增 reader；无数据迁移或写回。

## 第 2 步：从 Event 发现 Run，报告未结束和异常项

- 状态：pending。
- 交付：有界枚举、显式游标、逐 Run 快照、非终态边界及 projection 对照；坏历史返回安全错误项。
- 证据：错误终态 projection 不漏检、全终态页仍能翻页、并发追加不混合快照、锁等待与取消资源释放。
- 验证：内存/SQLite 共用扫描契约与双连接 integration tests；记录规模、耗时、环境与资源上限。
- 回退：停用扫描 service，不改已有单 Run 读写命令。

## 第 3 步：用户可以只读 replay/check，并看清它没有继续执行

- 状态：pending。
- 交付：bootstrap 组装、human/JSON 输出、命令帮助与退出码；默认数据库路径沿用 P1。
- 证据：没有 config/key 也能读取；不存在数据库不创建文件；K1-K6 之后重建最后事实且零额外模型、
  Tool、replace；旧 CLI/JSON 保持兼容，新命令名可作为转义后的普通目标。
- 验证：CLI integration、版本化 schema、hard-process suite、完整 pytest/Ruff/Pyright/governance、
  文档链接、站点 build 和 wheel smoke；远程 Windows/Linux CI。
- 回退：移除新增 CLI 注册；保留全部历史数据及既有命令。

## 文档和阶段边界

实现时同步 Spec 所列的四个文档表面；当前只记录 P2 设计启动，不把命令写成已可用。
本 Feature 完成后再接受 F-0022；不要把整个 P2 放进本 Plan。Checkpoint 的性能数据不足以支持引入时，
记录延期理由，不为关闭 Feature 添加缓存或迁移。

## 本次启动验证

已检查代码、测试、迁移、CLI 结构与 P1 恢复边界，并完成上述临时实验。

- `uv run python scripts/check_governance.py`：16 Specs、15 Plans、20 ADRs 通过；没有 active Plan。
- `uv run python scripts/check_docs.py`：155 个 Markdown 文件的本地链接通过。
- `npm run build --prefix=site`：48 页、Pagefind 和 sitemap 成功；只有既有的大 bundle 提示。
- `git diff --check`：通过。此次只有设计和状态文字，没有新增运行行为，所以不重复运行 P1 全量测试。

F-0021 的所有生产行为与验收测试均待实现。项目所有者已授权将设计稿提交并推送到独立分支供审阅；
Spec 和 Plan 保持 draft，ADR 保持 proposed，发布设计稿不代表接受设计或完成实现。
