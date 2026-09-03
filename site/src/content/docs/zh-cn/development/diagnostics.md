---
title: 为什么诊断日志不能决定 Run 发生了什么
description: 沿着 DiagnosticRecord、EventStore decorator 和 bootstrap，理解 stderr 日志怎样帮助排错，以及为什么 Run 状态仍只看 Event。
bearStatus: implemented
sourceRefs:
  - F-0031
  - ADR-0017
  - ADR-0002
  - ADR-0013
---

运行一次文件任务时，你现在会在 stderr 看到一行一条的 JSON。它帮助开发者回答“哪个组件、哪项操作
失败了”。但系统判断 Run 成功、失败或进行到哪里时，只读取 SQLite 中已经保存的 Event，不读取这些
日志。

```text
EventStore.append(event)
        |
        +-- transaction 失败 --> event.append_failed（说明写入失败，Run 中没有这条 Event）
        |
        +-- transaction 成功 --> projection + Event 已提交
                                   |
                                   +--> event.committed（帮助排错；缺失不影响已保存 Event）
```

## 一条 record 里有什么

`domain/diagnostics.py` 定义冻结的 `DiagnosticRecord`。它只允许：

- schema version、UTC 时间、级别、组件和操作；
- Run、Activity、Event、correlation 和 causation ID；
- Event type、sequence、Event commit 耗时和当前进程内 Activity 耗时；
- `ErrorCode` 和经过格式限制的异常类名。

这个类型没有 `message`、`details`、`payload`、`path`、`request`、`response` 或 `stack` 字段。调用方
因此不能顺手把 objective、模型回复、Tool 参数/结果、Provider body 或 `repr(error)` 塞进默认日志。
JSON adapter 还限制单行最多 4 KiB。

下面是一条形状示例，ID 会随 Run 改变：

```json
{"component":"event_store","event_type":"RunStarted","level":"info","name":"event.committed","operation":"event_append","operation_duration_ms":1,"run_id":"...","sequence":2,"schema_version":1}
```

需要完整执行内容时，使用 `bearagent run events RUN_ID --json`。那是显式读取本地 Event，不是可以随意
转发的脱敏日志。

## 代码怎样连接

| 位置 | 责任 |
|---|---|
| `domain/diagnostics.py` | 字段封闭的不可变 record |
| `ports/diagnostics.py` | sink protocol 与 fail-open `emit_safely` |
| `adapters/diagnostics.py` | stderr JSON Lines、Null sink 和 EventStore decorator |
| `bootstrap.py` | 选择默认 sink，装饰 production SQLite Store，记录组装/查询失败 |
| `interfaces/cli/main.py` | 在 Error renderer 前记录有限 CLI operation failure |

AgentLoop 没有 logger 分支。它仍只调用 EventStore port；production bootstrap 把 SQLite Store 包在
diagnostic decorator 里。同一个 Store 实例继续交给 AgentLoop 和 RunQueryService，所以诊断接线没有
产生第二条业务路径。

## 为什么先保存 Event，再输出日志

如果先打印 `RunSucceeded`，随后 SQLite transaction 回滚，日志会声称 Run 成功，但 EventStore 没有
这条事实。decorator 因而必须等 delegate `append` 成功返回后才输出 `event.committed`。

反过来，stderr 可能在 Event 提交后立刻故障，或者进程在输出前退出。这时日志会缺一行，但系统仍能
从 SQLite 查到这条 Event。简单说：日志可以漏记已经保存的 Event，却不能用来补充数据库里不存在的
Event。

## 为什么日志写失败不能让 Run 失败

代码中把这种处理称为 `fail-open`：`emit_safely` 会接住日志输出本身的普通异常。写 stderr、JSON
序列化或测试 sink 失败都不会：

- 回滚已经提交的 Event；
- 把成功 Run 改成失败；
- 触发第二次模型或 Tool 调用；
- 给 Reducer、恢复或 Policy 增加输入。

取消仍沿原业务调用传播；诊断层不把 `CancelledError` 改写成普通失败。

## Log 和 Trace 的当前边界

F-0031 可以用 started/terminal Event 对计算当前进程内的近似 Activity 耗时，但没有 span tree、sampling、
remote collector 或跨进程 propagation。完整 Trace、OpenTelemetry exporter 和跨版本比较仍属于 P5。

修改这条边界时，优先运行：

```powershell
uv run pytest tests/unit/test_diagnostics.py tests/security/test_diagnostics.py -q
uv run pytest tests/integration/test_run_cli.py -q
uv run python scripts/check_governance.py
```

重点不是“日志数量够不够多”，而是确认它只携带排错所需的最小字段，并且永远不能改变 Run 状态或
补写 Event。
