---
title: "Plan: inspectable Attempts and bounded safe retry"
status: active
plan_id: PLAN-F-0022
related_spec: F-0022
created: 2026-09-13
last_updated: 2026-09-30
---

# PLAN-F-0022：先让尝试可重建，再接入受限重试

关联 [F-0022](../specs/F-0022-bounded-attempt-retry.md) 与
[ADR-0021](../adr/ADR-0021-attempt-ledger-before-retry.md)。项目所有者于 2026-09-13 授权实现，2026-09-30 授权检查、修正、推送并提 PR。

## 已核对的起点

- F-0021 PR #26 于 2026-09-13 合入 main `28fc87305aed881cf999e570c3b130cae0eb402e`。
- 工作区原为干净的 F-0021 分支；已 fetch，并从 origin/main 建立
  `codex/F-0022-bounded-attempt-retry`。F-0021 Spec implemented、Plan completed，无 active Plan。
- 已检查 AgentLoop、ToolExecutor、Reducer、预算、Error、RunProfile、Event replay/hash、SQLite
  初始 migration 与现有失败测试。SDK retry 在三种模型 adapter 中均被禁止。
- 2026-09-13 定向基线测试：62 passed，0.86 秒。没有访问真实模型或用户运行数据库。

## 开始前接受

- [x] 接受 Spec 的 retry 范围、默认关闭、最多 3 次与共同 deadline。
- [x] 接受未知模型提交/用量不重发、写入结果不明停止整个 Run。
- [x] 接受 v5 Event、state hash v2、migration 2 和不能直接降级旧 writer 的边界。
- [x] Spec 改为 accepted、ADR 改为 accepted、本 Plan 改为唯一 active。

## 第 1 步：同一个 Activity 的两次尝试能保存、查询和重建

- 状态：实现已接通，验证结果见本页末尾。
- 交付：构造一个只读失败后成功的 v5 Run，在内存与 SQLite 保存两个 Attempt，并得到相同状态、
  两次预算、一份最终结果与可查询决定。暂不连接生产外部调用。
- 代码落点：domain 类型和 Event parser、runtime Reducer/预算/replay、store adapter/migration；
  生成新 schema，并保留旧 fixture。
- 连接：测试历史 -> 同一个 append/reducer -> 原子 projection -> Event-only replay。
- 重点测试：非法顺序/引用/重复决定、并发 Attempt、terminal 重复记账、v1-v4 hash 与计数不变、
  projection 缺失、迁移失败/断电边界与旧 writer 拒绝新格式。
- 验证：domain/schema、Reducer/budget、两种 store/replay contract、SQLite migration integration；
  再运行 Pyright 和 governance。
- 回退：暂不产生真实 v5 Run；临时测试库可重建。不能修改 0001 migration 或重写历史事实。

## 第 2 步：真实 ToolExecutor 在安全证据下重试，并在写入结果不明时停止

- 状态：实现已接通，验证结果见本页末尾。
- 交付：Fake 模型要求读取，真实 Executor 首次超时、第二次成功；模型只接收一次最终结果。写入
  后报错则停止整个 Run，后续模型或同一响应中排队的 Tool 均不执行。
- 代码落点：runtime 纯恢复规则、ToolExecutor 执行前记录边界、application AgentLoop/Context。
- 连接：Attempt failed -> 纯规则 -> 提交 Decision -> 可取消等待 -> 预算 -> prepare/Policy ->
  Started 提交 -> adapter。所有 I/O 仍在既有 port/adapter 后。
- 重点测试：重试前 Policy 改为拒绝、prepare 参数漂移、contract 漂移、Started append 失败、
  backoff 前后预算变化、共同 deadline、取消、前一个协程未退出、写入重复提议 canary。
- 验证：ToolExecutor security/integration、AgentLoop/Context unit、append 故障注入和临时文件断言。
- 回退：生产 profile 尚不开放重试；保留第 1 步只读能力。执行前记录钩子失败不能回退到不记录执行。

## 第 3 步：三种模型 adapter 只在明确未提交时重试，CLI 能配置和查看

- 状态：实现已接通，验证结果见本页末尾。
- 交付：已知未提交的短暂失败可有限重发同一 ModelRequest，未知用量或部分流停止；RunProfile v3、
  bootstrap、human/JSON attempts 查询和帮助接通。默认 max_attempts=1。
- 代码落点：模型内部失败证据与三协议 adapter、AgentLoop、RunProfile/加载校验、application 查询、CLI。
- 连接：adapter 传输事实 -> 内部失败类型 -> 同一恢复规则；CLI 通过 application 查询 Event-derived
  数据，不接触 Provider SDK、workspace 或 SQL。
- 重点测试：三协议模拟连接失败/429/5xx/部分流/timeout、未知 usage、实际请求次数、SDK retry=0、
  逻辑 ToolCall 与结果配对、旧 profile/JSON、分页/缺库/无凭据和敏感 canary。
- 验证：model port 共用契约、生产 composition 的模拟 transport 集成、CLI/schema 和 wheel smoke；
  不执行真实付费请求。
- 回退：max_attempts=1 停用重试；已有新库仍用新 reader。旧二进制回退按 Spec 的一致备份方案。

## 第 4 步：验证新增中断边界并同步读者文档

- 状态：实现已接通，验证结果见本页末尾。
- 交付：失败 Event 已保存、决定已保存、下一 Started 已保存等边界强制退出进程，再用新进程只读
  replay/check/attempts；最后状态与副作用次数一致，不自动续跑。
- 重点证据：故障位置、输入 hash、真值、规则版本、预期/实际调用次数和额外成本；真值不传入规则。
- 文档：按 Spec 四个表面更新路径；清楚区分本 Feature 进程内 retry、F-0023 核对/UNKNOWN、
  F-0024 控制命令与恢复策略比较。README 仅在实际读者入口有必要变化时更新。
- 验证：完整离线 pytest、Ruff、Pyright、lock、governance、文档链接、schema、站点构建、wheel smoke；
  Windows/Linux CI 在获得发布授权后核对。站点说明更新后检查浅色/深色与窄屏。
- 回退：保留全部 Event 证据；不执行恢复或清理用户文件。完成前逐项填写下表和实际检查结果。

## 跨切片检查

| 风险面 | 要求 | 当前证据 |
|---|---|---|
| Persistence / recovery | Attempt、Decision 与 projection 一致；中断后零额外执行 | attempt store contract、migration rollback、5 个子进程退出边界通过 |
| Permission / security | 每次 prepare/Policy；失败存储不得绕过；写入不明立即停下 | Policy/参数/契约变化与 6 个 append 失败边界、实际写入 canary 通过 |
| Timeout / cancel / limits | 全部尝试共用 deadline；等待可取消；计数不重置 | Attempt cap、调用预算、deadline、取消、前协程 cleanup 通过；共享五类预算检查继续复用 |
| Migration / rollback | 旧历史/hash 不变；migration 原子性；新库拒绝旧 writer | 旧 hash/历史契约与迁移回滚通过；旧 writer 的 version 1 guard 拒绝 version 2 ledger |
| Logs / trace | 固定 envelope，不新增 payload 或路径；无需完整 Trace 系统 | 既有诊断安全 suite 与新查询 canary 通过，日志字段白名单未扩大 |
| Documentation | Spec 所列四面更新；不能把草案写成已实现或声称 P2 关闭 | 四面路径已更新，明确进程内 retry；P2 仍进行中，发布/CI 待核对 |

## 已运行的设计基线检查

```console
uv run pytest tests/unit/test_agent_loop.py tests/unit/test_budgets.py tests/unit/test_run_reducer.py tests/recovery/test_agent_loop_boundaries.py --basetemp=.pytest-tmp-f22-discovery -o cache_dir=.pytest-state-f22-discovery -q
```

结果：62 passed，0.86 秒。该结果属于未改生产代码的 main 基线，不是 F-0022 的完成证据。
草案检查：`uv run python scripts/check_governance.py` 通过（17 Specs、16 Plans、21 ADRs）；
`uv run python scripts/check_docs.py` 通过（158 个 Markdown 文件）；`git diff --check` 通过。
以上为设计时的历史基线，不能作为本次实现通过的证据。

## 2026-09-30 实现审查与发布验证

步骤 1 对应 tests/contract/test_attempt_store_contract.py、tests/security/test_attempt_events.py、
tests/integration/test_attempt_migration.py；步骤 2 对应 tests/integration/test_attempt_execution.py；
步骤 3 对应 tests/contract/test_model_attempt_evidence.py、tests/integration/test_retry_profile.py、
tests/integration/test_attempt_cli.py；步骤 4 对应 tests/recovery/test_attempt_crash.py 与四个文档表面。

审查修正异常链误判：读写失败中更早的 ConnectError 不得成为未提交证据。新增六个三协议
MockTransport 回归，修正前均发生 3 次请求，修正后均为 1 次且 usage/submission 明确未知。
同时修正 migration 测试的未来版本号，扩充 installed wheel 的 attempts 查询 smoke。
真实 SDK 测试提高模拟调用 timeout，避免首次资源加载超过一秒 fixture；没有放宽生产默认值。

本地验证（2026-09-30）：

- `uv run pytest --basetemp=.pytest-tmp-f22-final -o cache_dir=.pytest-state-f22-final -q`：638 passed，104.92 秒。
- `uv run ruff check .`、`uv run ruff format --check .`、`uv run pyright`：通过，类型检查零错误/警告。
- `uv lock --check --offline`：34 packages，锁文件一致；未改生产依赖。
- `uv run python scripts/check_governance.py`：17 Specs、16 Plans、21 ADRs。
- `uv run python scripts/check_docs.py`：159 个 Markdown 文件链接通过。
- `uv build --offline`：sdist 与 wheel 成功，包含 migration 2。
- wheel 安装到 `.uv-cache/f22-wheel-review`，隔离 Python import 确认为安装产物；
  `scripts/smoke_wheel_cli.py` 通过 run/inspect/events/replay/check/attempts，无真实模型调用。
- `npm run build`：49 页 Starlight 成功。Windows 缓存写入权限导致首次失败，授权环境重跑成功。
- 浏览器实测新导读在 1280px/390px 浅色与深色下可读，窄屏无页面横向溢出，代码块独立横向滚动。

远端 Windows/Linux CI 尚待 PR 触发，步骤 4 与本 Plan 保持 active，完成后再关闭。
