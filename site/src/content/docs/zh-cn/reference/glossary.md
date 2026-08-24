---
title: 术语表
description: BearAgent 代码和文档中保留的核心术语，以及它们在一次任务里的含义。
bearStatus: design
sourceRefs:
  - architecture/overview
  - F-0002
---

术语表用于保持代码和文档一致，不要求在每一段都堆满术语。面向初学者的页面应先讲场景，再在
需要精确指代时使用这些名字。

| 术语 | 在 BearAgent 中表示什么 |
|---|---|
| Runtime / 运行时 | 组织模型和工具调用，并负责状态、预算、记录和权限的系统 |
| Agent | 模型、可用工具、说明和限制的配置，不是某次执行 |
| Session | 一段连续对话，可以包含多个 Run |
| Run | 处理一条用户请求的一次执行 |
| Activity | Run 中的一次模型调用或工具调用 |
| Attempt | 某个 Activity 的一次执行尝试；重试会新建 Attempt |
| Event | 已经发生并按 sequence 排序的不可变事实 |
| Reducer | 逐条读取 Event 并计算 `RunState` 的纯函数，不执行 I/O |
| Budget | 创建 Run 时确定的资源上限，以及 Event 已记录的实际用量 |
| port | Runtime 对外部能力提出的接口要求，如模型调用或 Event 保存 |
| adapter | port 的一种具体实现，如真实模型、测试模型、SQLite 或内存存储 |
| schema | 数据允许有哪些字段、类型和组合的可验证定义 |
| Command | 希望系统执行的动作，可以被拒绝；未必成为 Event |
| Checkpoint | 某个 Event sequence 对应的状态快照，可从 Event 重建 |
| Artifact | Run 生成、可由用户取回的文件或结构化产物 |
| Receipt | 外部系统返回、可用于确认操作结果的证据 |
| Reconcile | 利用文件状态、幂等键或 Receipt 核对操作究竟是否发生 |
| `UNKNOWN` | 外部操作可能已发生，但 Runtime 暂时无法确认结果 |
| RecoveryDecision | 根据已保存事实选择复用、重试、reconcile 或停下的决定 |
| Tool | 执行读取、写入或其他外部动作的接口 |
| Skill | 可复用的说明、知识和流程提示，不包含权限 |
| Grant | 对主体、动作、资源和限制的授权 |
| Approval | 用户对一次绑定具体 Run、Tool call 和规范化参数的授权决定 |
| Workflow | 由代码确定阶段顺序的流程，不等于 Agent Loop |

代码中不使用 Task、Job、Thread 或 Turn 代替 Run，也不使用 Capability 同时表示业务流程和安全
权限。普通解释可以说“任务”，但涉及状态或接口时应明确写 `Run`。
