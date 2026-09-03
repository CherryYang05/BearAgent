---
title: "ADR-0017: Use Events to confirm execution and diagnostics only for troubleshooting"
status: accepted
date: 2026-09-02
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0017：系统只用 Event 确认执行结果，诊断日志只帮助排错

## 要解决的问题

BearAgent 已用 EventStore 保存模型、Tool、预算、Error 和 Artifact 事实，但配置读取、数据库初始化与
adapter 内部错误可能发生在 Event 之前或之外。若 Runtime 再写一份包含请求、响应和状态的通用日志，
Event、日志和 CLI 会形成三套含义；崩溃后调用方还可能把先于 transaction 输出的日志误当成已提交事实。

另一方面，完全没有统一运行诊断会让开发者难以定位 bootstrap、persistence 和 CLI 边界失败。现在必须
说清楚：哪些信息会影响系统对 Run 的判断，哪些信息只给开发者排错，以及两者如何用 ID 关联。

## 选择时最看重什么

- 可维护性：Run 状态只根据 Event 判断，不让每个模块自由发明日志字段；
- 恢复语义：日志存在、缺失或乱序都不影响 Reducer 和恢复判断；
- 安全：默认结构从类型上排除正文、原始异常、路径和凭据；
- 复杂度/交付时间：只用标准库 stderr，不引入遥测 SDK、collector 或日志数据库；
- 兼容与迁移：不改变 Event、CLI JSON、SQLite schema 和历史 Run。

## 比较过的方案

### 方案 A：把 Agent Loop 全量复制为 JSONL 日志

它易于人工查看，也能携带 Prompt、Tool 参数和响应。但这些内容已经在 Event 中有明确版本和 byte
边界；复制会增加泄密面、顺序分叉和日志保留责任，且无法与 Event transaction 原子提交。

### 方案 B：Event 保存执行记录，固定字段日志帮助排错

已提交 Event 只导出 envelope、关联 ID、耗时与安全错误码；没有 Event 归宿的 bootstrap/adapter/CLI
问题使用单独 operation record。两类 record 都不能参与状态和恢复。代价是日志不能单独重放完整 Run，
排查业务事实时仍需使用 `inspect/events`。

### 方案 C：立即接入 OpenTelemetry logs、metrics 和 traces

它能提供 exporter、span 和现成后端，但 P1 只有单进程 CLI，尚无 collector、sampling、远程数据边界
或运维需求。现在引入会把遥测生命周期和新生产依赖带入 Runtime；P5 才有跨版本 trace 的退出证据。

## 决定

选择方案 B，并规定：

1. 系统只根据 Event 判断 Run 做到了哪里、用了多少预算，以及中断后能否继续。DiagnosticRecord 只在
   当前进程中输出，即使没有写出来或后来被清理，也不能进入 Reducer、Context、Checkpoint、恢复或
   授权流程。
2. EventStore decorator 只能在 delegate append 成功后发出 `event.committed`。append 失败必须使用
   `event.append_failed`，不得假装 Event 已存在。
3. DiagnosticRecord 是冻结的 BearAgent 类型，只允许固定版本、时间、级别、组件、操作、关联 ID、
   Event 元数据、耗时、错误码和异常类型。它没有任意 message、details 或 payload 容器。
4. 默认 adapter 把一行一个 JSON object 写到 stderr，并限制整行 byte。CLI stdout contract 不变。
5. 所有 sink 调用都经 fail-open 隔离；sink 失败不能回滚 Event、终止 Run、改变 query，也不能触发重试。
6. bootstrap 是默认 sink 与 EventStore decorator 的 composition root。domain、runtime 和 application
   不导入具体日志 adapter；AgentLoop 不增加 logger 分支。
7. Activity 耗时可以由同一进程中已提交的 started/terminal Event 对计算，但只是诊断近似值；Event
   `occurred_at` 和 sequence 仍是事实。缺失 started record 时省略耗时，不猜测。
8. 默认不记录 traceback、Prompt、模型文本、Tool 参数/结果、Error message/details、Provider response、
   路径、配置或环境变量。未来 debug traceback 必须显式启用并另行定义脱敏和保留边界。
9. P5 可以增加从 committed Event 派生的 ledger exporter 和可选 OpenTelemetry span；不得让 exporter
   反向成为 Runtime 依赖或恢复事实。

这个决定与 DeepSeek Harness 把 session ledger 与 ops channel 分开的做法一致，也采用 Claude Code
默认关闭详细 trace 和内容导出的安全方向；外部实现只提供比较，不证明 BearAgent 当前能力：

- <https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/session-telemetry.md>
- <https://code.claude.com/docs/en/monitoring-usage>

## 带来的影响

### 得到的好处

- 运行失败有统一、可关联且可机器解析的 stderr 信号；
- Event payload 不会被复制到第二套默认记录；
- sink 不可用时 Runtime 行为保持不变；
- 未来 OTel exporter 可以接在稳定 record/Event 投影之后，而不是侵入 AgentLoop。

### 接受的代价

- stderr JSON Lines 不提供文件轮转、查询 UI 或跨进程 trace；
- 日志不能独立重放 Run，完整调查仍要查询 EventStore；
- Event 提交后，进程可能在日志输出前立即退出，因此少一行日志是允许的；已提交 Event 不受影响；
- Activity duration 是当前进程内近似值，不是持久 SLA 证据。

## 迁移和回退

没有数据库、Event 或 CLI JSON migration。默认 stderr 输出是新增的可观察行为；嵌入调用可注入 Null
sink。回退可以移除 decorator 和 adapter，但必须保留既有 Event/Reducer/CLI 查询语义，不能从日志补写
或删除历史事实。

## 怎样验证

- spy store 证明 committed record 只在 delegate append 成功后出现；
- failing sink 证明 Event、query 和 Run 结果不受影响；
- security tests 向 objective、Tool payload、异常、路径和环境注入 marker，再扫描全部 diagnostics；
- CLI integration 证明 stdout 仍是原 human/JSON contract，stderr 每条 diagnostic 可解析且字段封闭；
- schema、migration、import-boundary、Ruff、Pyright、pytest、governance 和文档构建继续通过；
- P5 开始时重新评估 OTel、远程 exporter、sampling、trace propagation 和保留期。

项目所有者于 2026-09-02 要求按该收窄方案实现，接受本决定。
