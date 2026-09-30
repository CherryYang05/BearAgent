---
title: "ADR-0021: persist Attempt facts and validate evidence before retry"
status: accepted
date: 2026-09-13
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0021：先保存每次 Attempt 的事实，再根据证据决定是否重试

关联 [F-0022](../specs/F-0022-bounded-attempt-retry.md)。项目所有者于 2026-09-13 接受本决定。

## 为什么必须统一决定

当前 AgentLoop 把一次 Activity 当作一次调用：requested 时增加预算，terminal 时保存结果。
如果只在模型或 Tool adapter 中补循环，Event 会显示一次调用，实际却发生多次。把每次 retry
建成新 Activity 又会丢失同一个逻辑请求的关系，使 ContextBuilder 重复生成结果。

另一个问题是写入超时。ToolExecutor 已返回失败不代表文件没有更新；把失败交回模型继续，模型
可能重新提出同一写入。F-0022 需要在没有 Receipt/reconcile 的阶段明确停下，给 F-0023 留下事实。

## 比较过的方案

| 方案 | 优点 | 代价与失败方式 |
|---|---|---|
| adapter 内依照 retryable 自动循环 | 改动少，短暂错误可能消失 | 隐藏次数、账单与副作用；预算和 Event 不一致 |
| 每次重试都创建新的 Activity | 复用旧状态类型 | 同一模型/Tool 请求身份断裂，Context 可能重复结果，恢复依据难查 |
| 一个 Activity 下保存多个 Attempt，由纯规则决定下一步 | 逻辑结果唯一，次数与失败可查，旧事实不被覆盖 | 新 Event、projection、预算版本和迁移必须一起验证 |
| 引入通用 graph/workflow retry engine | 可利用现成调度设施 | 仍需映射 BearAgent Event、Policy、预算与副作用；引入没有当前需求支持的框架边界 |

## 决定

选择第三个方案。Attempt 是进入执行流程的一次尝试，Started 表示通过执行前检查且即将调用
adapter；它不能证明远端已经接收。未通过 prepare/Policy 的尝试可以没有 Started。

Application 负责持久化和串行调度，runtime 纯函数负责基于可信证据选择 RETRY、RETURN_TO_MODEL
或 STOP_RUN，ToolExecutor 负责每次真正执行前的 prepare、Policy 和限额。恢复规则不接受自由文本
指令或 SDK 对象，日志也不参与决定。SDK 与 transport 不再有第二层重试。

只有 Attempt terminal 与 RecoveryDecision 都成功提交后才可安排下一次尝试。retry 决定绑定
失败 Event 和唯一下一 Attempt，不能重复消费。等待之后重新检查预算，再进入 ToolExecutor；每次
Started 的执行证据必须先保存。任何 append 失败都停止，不把事实存储错误转换成可继续的 Tool 错误。

恢复语义与权限分开。READ_ONLY 只说明副作用范围允许考虑重试，不替代 Policy。IDEMPOTENT 或
RECONCILABLE 声明不构成幂等键/Receipt 证据，本 Feature 不开启这些写入重试。写入已经进入 adapter
却没有可靠成功结果时，停止全部后续调度，保存 EFFECT_INDETERMINATE 与停止理由。

F-0022 不新增 Run UNKNOWN 状态。RunFailed 表示协调器停止，其 error 必须明确外部效果不明，不能
解释为文件未更新。F-0023 才设计可核对和可处理的 UNKNOWN；F-0024 才恢复中断 Run 的执行。

## 有界执行与模型费用

max_attempts 默认 1，用户在 RunProfile v3 显式启用，最大 3。一次 Activity 首次请求时，用最大
尝试次数乘以单次 timeout，再加各次退避上限，得到固定执行窗口，并受 Run 总期限约束。每次
调用仍有自己的 timeout，不能超过窗口余量；首次超时后可以重试，但重试不会延长整个窗口。
使用有上限的指数退避和 full jitter；抽样结果存入决定，重放时只读、不重新计算随机时间。

每次 AttemptRequested 占用原来的模型/Tool 计数预算，已知用量在 Attempt terminal 入账；逻辑
Activity terminal 不重复记账。未知 usage 单独标明。模型生成具有收费和不确定结果，不能简单等同
只读文件；本次只有可信 adapter 明确证明未提交模型请求的短暂失败可自动重试。429、5xx、未收到
文本或 retryable=true 均不能单独证明这一点。

这一限制牺牲部分可用性，换来可审查的自动重发边界。以后若要允许请求已提交的模型重试，需要单独
接受保守用量预留或可靠账单核对方案，不能在本 Feature 用零 usage 占位扩展许可。

## 版本、迁移与回退

v1-v4 保留原 Event 和预算含义；v5 一个 Run 内统一使用新语义。新增恢复声明进入版本化的可信
contract snapshot，不重新解释历史 fingerprint。旧历史没有 Attempt 时，查询明确报告未记录。

SQLite migration 2 添加派生查询数据和必要版本信息，Event 不重写；append 和 projection 原子
提交，迁移失败全部回滚。旧 RunState 的 state hash v1 固定，新状态使用 v2，不默默改变 v1 输入。
旧 inspect/events 的公共格式保持兼容，新增细节通过版本化 attempts 查询提供。

停止 writer 后先保存一致备份，再迁移。关闭 retry 不会还原持久格式；降级旧二进制必须恢复升级前
备份或换新库，保留升级后的数据库副本。不能删除新 Event、伪造 schema version 或允许旧 writer
继续修改新库。备份之后的事实不能声称在降级后仍然存在。

## 怎样验证

用同一组 Event 在内存和 SQLite 验证预算、引用、状态与 hash；用 Fake Provider、真实 Executor
和临时 workspace 验证失败后成功、永久拒绝、写入结果不明、未知模型用量及上限耗尽。
对失败 terminal、决定、下一 Started 的保存边界注入异常与进程退出，断言外部调用次数，而不只
检查最终状态。F-0021 的只读重建必须继续保证零额外执行。验收细目见 Spec 与 Plan。

## 外部资料与适用范围

以下资料于 2026-09-13 核对，只用于比较设计，不说明 BearAgent 已有这些能力：

- [LangGraph fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance)
  展示按异常与退避控制 retry、记录 attempt 序号和单次 timeout。本项目还需要跨尝试的共同期限、
  持久预算和外部副作用证据，因此不直接照搬节点默认重试规则。
- [LangGraph 发布记录](https://github.com/langchain-ai/langgraph/releases) 当日可见 8 月的
  langgraph 1.2.11、SDK 0.4.4 等近期发布，是仍有维护活动的参考；这不证明框架适合成为本项目内核。
- [AWS：Timeouts, retries, and backoff with jitter](https://d1.awsstatic.com/builderslibrary/pdfs/timeouts-retries-and-backoff-with-jitter.pdf)
  讨论重试放大负载、有副作用调用需要幂等性，以及有界退避与 jitter。本方案据此只保留一层重试，
  对无核对证据的写入停止，对退避设上限；这些具体边界仍由 BearAgent 自己的测试验证。
