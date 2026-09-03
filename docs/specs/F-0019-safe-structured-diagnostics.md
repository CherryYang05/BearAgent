---
title: "Feature: Safe structured operational diagnostics"
status: implemented
spec_id: F-0019
milestone: P1
change_level: S2
owner: CherryYang05
created: 2026-09-02
last_updated: 2026-09-04
implemented_in: 5d9da00
related_adrs: [ADR-0002, ADR-0007, ADR-0013, ADR-0014, ADR-0017]
---

# F-0019：安全输出结构化运行诊断，而不复制 Event 内容

## 1. 问题与证据

`run/inspect/events` 已经可以查询一次 Run 的持久事实，但配置读取、SQLite 初始化、CLI 边界和
EventStore adapter 自身失败时，可能还没有 Event 可以查询。开发者只能看到最终安全 Error，无法把
失败定位到具体组件和操作。

F-0016 已要求默认结构化日志只记录 ID、Event type、sequence、耗时和有限错误码，当前源码却没有统一
的诊断 record、sink 或 production wiring。若每个模块临时使用 `print`、`console.error` 或任意
`logging` extra，Prompt、Tool 参数、Provider 响应和原始异常可能被复制到第二套记录中。

## 2. 目标与非目标

### 本次交付

- G-1：定义冻结、字段封闭且有 byte 上限的 `DiagnosticRecord`；它只帮助排错，不作为系统判断
  Run 状态的记录；
- G-2：默认把结构化 JSON Lines 写到 stderr，保持 CLI stdout 的 human/JSON contract 不变；
- G-3：Event 成功提交后输出 Event envelope、Activity ID、耗时和安全错误码，不复制 payload；
- G-4：配置、组装、查询和 EventStore 失败输出组件、操作、错误码和异常类型，不输出异常文本或堆栈；
- G-5：任何诊断 sink 失败都与 Run、Event transaction、查询结果和 CLI Error 隔离；
- G-6：保留注入 `NullDiagnosticSink` 或测试 sink 的入口，便于嵌入调用和确定性测试。

### 本次不做

- NG-1：不新增日志数据库、日志文件、轮转、保留期、后台上传或远程 collector；
- NG-2：不新增 OpenTelemetry、span exporter、sampling、跨进程 propagation 或 trace UI；
- NG-3：不新增 `trace` CLI，也不从日志重建 Run、恢复 Activity、决定 retry 或授予权限；
- NG-4：不记录 Prompt、模型文本、Tool 参数、ToolResult、Provider 原始响应、路径、凭据或环境变量；
- NG-5：不改变 Event schema、Reducer、projection、SQLite migration、P2 恢复语义或 P3 授权语义；
- NG-6：默认不记录 traceback；未来若需要本地 debug traceback，必须单独定义启用和脱敏边界。

## 3. 场景与可观察行为

### Scenario A：跟随一次正常 Run

- FR-1：每条 Event 只能在对应 `EventStore.append` 成功返回后产生 `event.committed` record；
- FR-2：record 包含 `run_id`、`event_id`、`event_type`、`sequence`、correlation/causation ID，以及可用的
  `activity_id`、Event commit 耗时和 Activity 耗时；
- FR-3：失败 Event 可以增加领域 `error_code`，但不能复制 Error message/details 或 Event payload。

### Scenario B：Event 尚未建立时失败

- FR-4：bootstrap 或 CLI 边界输出 `operation.failed` record；没有 RunId 时明确省略该字段，不伪造 ID；
- FR-5：未知异常只输出 `internal_error` 和经过限制的异常类名，不输出 `str(error)`、`repr(error)` 或
  traceback。

### Scenario C：诊断输出不可用

- FR-6：sink 抛错、序列化失败或 stderr 不可写时，原业务调用继续返回原来的结果或抛出原来的异常；
- FR-7：诊断失败不追加 Event，不改变 projection，也不触发第二次模型或 Tool 调用。

## 4. 对外入口与模块连接

新增 BearAgent `DiagnosticRecord`、`DiagnosticSink` port、JSON Lines/Null adapter 和 EventStore
decorator。`bootstrap.py` 仍是唯一 production composition root；`build_run_services` 与
`build_run_query_service` 增加可选 sink 注入，省略时使用 stderr JSON Lines。

CLI 命令和 JSON schema 不增加字段。结构化诊断只进入 stderr；`--json` stdout 仍只有一个 command
result/error object。

## 5. 状态与持久化

Diagnostic record 只在当前进程中输出，不保存到数据库。即使某一行没有写出来、写入失败或后来被
清理，Run 状态也不能因此变化。它不是 Event，不分配 Event sequence，也不进入 SQLite、Reducer、
Checkpoint、Context 或 Artifact。Event 与 projection 的 transaction 边界不变。

## 6. 失败、恢复与安全边界

- Event 相关 record 必须 post-commit，不能把尚未提交的 Event 描述成事实；append 失败使用不同的
  `event.append_failed` 名称；
- sink 调用使用 fail-open 隔离，只捕获诊断 adapter 自身的普通异常；取消仍按原调用路径传播；
- record 模型拒绝未知字段、无时区时间、负耗时和超长/非法标识符；JSON Line 还有独立 byte 上限；
- record 没有 message、details、payload、path、request、response 或 stack 字段，从类型上阻止调用者
  把任意内容塞入默认日志；
- 日志不是恢复证据。进程退出后只相信已提交 Event；日志存在或缺失都不能改变 retry、reconcile、
  `UNKNOWN` 或授权决定。

## 7. 上线与回退

不需要 migration 或数据回填。上线只增加 stderr 诊断；现有 stdout、Event 和数据库保持兼容。回退时
可以撤销 composition wiring 和新增模块，已有数据库与 Event 不需要修改。若下游不希望接收 stderr，
嵌入调用可以显式注入 `NullDiagnosticSink`。

## 8. 验收标准与证据

| AC | 可判断的结果 | 证据路径或命令 |
|---|---|---|
| AC-1 | 正常 Run 的已提交 Event 产生有序、安全的结构化 record，失败 Event 带有限错误码 | diagnostics unit/integration tests |
| AC-2 | record 不包含 objective、模型文本、Tool 参数/结果、原始异常、路径或 secret | `tests/security/test_diagnostics.py` |
| AC-3 | append 失败不产生 committed record；sink 失败不改变 append/query/Run 结果 | diagnostics unit/contract tests |
| AC-4 | CLI stdout contract 不变，stderr record 可独立解析，安全 CLI Error 不泄漏原始异常 | CLI integration/security tests |
| AC-5 | Event/Reducer/SQLite schema 与 migration 无变化，架构 import boundary 继续通过 | schema generators + architecture tests |
| AC-6 | Ruff、format、Pyright、pytest、governance、docs links 和受影响站点构建通过 | 最终验证命令 |

## 9. 文档影响

| 表面 | 更新路径，或 `N/A` + 原因 |
|---|---|
| Engineering `docs/` | 本 Spec、ADR-0017、Plan、`docs/architecture/overview.md`、`docs/project/roadmap.md` |
| Site beginner path | `site/src/content/docs/zh-cn/guides/cli.md`：说明 stdout/stderr 与日志不是恢复事实 |
| Site developer docs | 新增 diagnostics 开发者页并从 development index/Agent Loop 页面连接 |
| Site current status | `site/src/content/docs/zh-cn/project/status.md`：记录最小结构化诊断边界 |
| Generated reference | N/A：不把 DiagnosticRecord 加入公开 domain/CLI schema contract |

README 为 N/A：安装和最短 CLI 路径不变，这不是新的产品主能力。

## 10. 尚未决定的问题

- OQ-1：N/A。默认 sink、字段白名单、post-commit 和 P5 边界由 ADR-0017 决定；远程 exporter、sampling
  和 traceback 需求必须由后续 Feature 重新评估。
