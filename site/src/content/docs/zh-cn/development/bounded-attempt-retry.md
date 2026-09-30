---
title: 一次读取失败，什么时候可以再试
description: 跟随 AttemptRunner、恢复决定和预算，检查进程内重试为什么不会绕过 Tool Policy。
bearStatus: implemented
sourceRefs:
  - F-0022
  - PLAN-F-0022
  - ADR-0021
---

假设模型要求读取一份文档。第一次读取超时，第二次成功：用户看到一个读取 Activity、两个
Attempt 和一个最终 ToolResult。Activity 是逻辑操作；Attempt 是一次进入执行流程的尝试。
失败会保留，Tool 调用预算也会增加两次。

F-0022 实现的是当前进程内的有限重试。默认只尝试一次；显式配置最多三次。重启后查询历史不会
自动续跑。写入结果核对、Receipt、正式 `UNKNOWN` 和控制命令仍属于后续 Feature。

## 先留下失败，再决定下一步

```text
ToolCallRequested / Started       逻辑 Activity 各记录一次
  AttemptRequested               预留一次调用预算
  prepare -> Policy
  AttemptStarted                 提交成功才允许进入 adapter
  AttemptFailed
  RecoveryDecisionRecorded       retry，并记录实际等待时间
  等待 -> 再查预算与共同 deadline
  AttemptRequested
  prepare -> Policy              不能复用上一次的允许决定
  AttemptStarted
  AttemptSucceeded
ToolCallCompleted                只有最终结果进入下一轮 Context
```

成功不需要恢复决定。失败后可以选择 `retry`、`return_to_model` 或 `stop_run`。决定引用同一个
Run 中的失败 Event、Attempt、契约 hash、规则版本和最后 sequence。Reducer 检查这些引用与当时
的预算，不接受跨 Run 引用、跳号、并发 Attempt 或重复消费同一个重试决定。

## 哪些失败可以再试

| 情况 | 当前处理 |
|---|---|
| 只读 Tool 短暂失败，上一协程已退出 | 在预算、次数和期限内再试；重新 prepare 和 Policy |
| 模型传输明确在连接阶段失败，已知没有提交和用量 | 重发同一个 ModelRequest，仍消耗一次调用预算 |
| 模型读写传输失败、限流、5xx、部分流或提交情况未知 | 停止 Run，不重新提交 |
| 权限拒绝、参数错误或 prepare/契约改变 | 不自动重试；普通 Tool 失败可交回模型 |
| 写入进入 adapter 后失败 | 保存 `effect_indeterminate` 并停止整个 Run |
| Event 保存失败、取消或进程退出 | 停在最后已提交事实，不启动后续执行 |

异常消息和 `retryable=true` 都不能证明请求没提交。adapter 只把具体连接阶段错误作为未提交证据。
如果异常链中先有连接错误，后来出现读写错误，后者仍然意味着提交情况不明。响应头已经到达后，
即使还没翻译出文本，也不能再把请求当作未提交。

三种生产协议的 SDK 都关闭内部 retry。Runtime 不换 Provider，不修改 Prompt，也不把失败流中
尚未完成的 Tool call 交给 Executor。

## 重试不会刷新预算或期限

v5 在 `AttemptRequested` 记一次模型或 Tool 调用，在 Attempt 结束时记一次已知 token 和费用。
逻辑 Activity 结束只校验最终结果，不再累加。v1-v4 历史继续在原来的 Activity Event 记账。

一个 Activity 的 deadline 从第一次逻辑请求固定：最多尝试次数乘单次 timeout，加退避上限之和，
再受 Run 总时间限制。每次调用使用单次 timeout 与剩余窗口中的较小值。等待前后和 dispatch 前
都重新检查，不能通过第三次尝试重新获得完整执行窗口。

退避使用指数上限和 full jitter，实际等待写入决定。replay 只读这个值，不随机抽样，也不等待。
模型未报告的用量仍是未知；账面总量只代表已知部分，不能据此声称远端账单为零。

## 写入失败为什么停下整个 Run

`workspace.write` 可能已替换目标文件，随后才报错。当前没有结果核对机制，因此不重复写入，
也不执行同一模型响应中排队的其他 Tool 或下一次模型调用。

`RunFailed` 表示协调器已停止，不表示文件没有变化。若失败事实也没保存成功，查询可能仍显示
`running`。F-0023 将单独定义 Receipt、核对和 `UNKNOWN`；F-0024 再提供执行控制。

## 从哪些文件读代码

| 文件 | 负责什么 |
|---|---|
| `domain/attempts.py` | 冻结的 Attempt、恢复契约、失败证据和 RetryPolicy |
| `runtime/attempts.py` | 根据已提交证据计算 deadline 与下一步 |
| `runtime/attempt_reducer.py` | 校验 v5 转换、引用、预算和最终结果 hash |
| `application/attempt_execution.py` | 串行执行、保存决定、可取消等待与重查边界 |
| `runtime/tool_executor.py` | 继续统一 lookup、prepare、Policy、timeout 和 adapter 执行 |
| `adapters/model/_common.py` | 把传输阶段翻译成内部提交证据，不解析错误消息 |
| `adapters/sqlite/migrations/0002_attempt_projections.sql` | 增加派生的 v5 状态缓存，不改历史 Event |
| `application/run_replay.py` | 从 Event 重建后输出内容受限的 Attempt 摘要 |

## 查询、升级和最小实验

```console
uv run bearagent run attempts RUN_ID --json
uv run pytest tests/integration/test_attempt_execution.py tests/contract/test_model_attempt_evidence.py -q
uv run pytest tests/recovery/test_attempt_crash.py tests/integration/test_attempt_migration.py -q
```

`attempts` 默认一页 100 条，最多 1,000 条；按 `requested_sequence` 翻页。它不返回目标、请求参数、
ToolResult 或原始异常，也不读取模型配置。旧 Run 显示 `legacy_not_recorded`，不会补造 Attempt ID。
完整历史仍受 10,000 条 Event、16 MiB 和 30 秒重建期限限制，分页不会避开重建成本。

新 Run 写 Event v5，使用独立的 `RunStateV5` 和 state hash format v2。旧 Event 与旧状态的固定
hash 保持不变。公开 schema 增加新类型、联合分支和稳定错误码；没有给旧 RunState 添加默认字段。

升级前停止 writer，用 SQLite backup API 或关闭连接后的完整备份保存一致数据库。migration 2
在事务内提交；失败全部回滚。把 `max_attempts` 改成 1 只关闭重试，不会把数据库降回旧版本。
旧 writer 拒绝新 migration；降级需要恢复升级前备份或使用新库，并保留升级后的副本供检查。

配置步骤见[命令行手册](/zh-cn/guides/cli/)，概念解释见
[失败后先问哪三个问题](/zh-cn/learn/recovery-authority-isolation/)。
