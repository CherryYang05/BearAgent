---
title: 术语表
description: BearAgent 中稳定使用的核心领域术语。
bearStatus: design
sourceRefs:
  - architecture/overview
---

这些术语来自 BearAgent 已接受的架构。文档和代码不应随意引入同义词。

| 术语 | 定义 |
|---|---|
| Agent | 使用模型、工具和策略完成目标的配置，不是一次执行 |
| Session | 用户连续对话的容器，可以包含多个 Run |
| Run | 对一条用户请求的一次可持久化执行 |
| Activity | 一个需要跟踪生命周期的模型调用或工具调用 |
| Event | 已经发生、不可变、带顺序的事实 |
| Command | 希望系统执行的动作，可以被拒绝 |
| Checkpoint | 某个 Event sequence 上的派生状态快照，可重建 |
| Artifact | Run 生成并由用户取回的文件或结构化产物 |
| Tool | 具有输入 schema 和执行语义的动作接口 |
| Skill | 可按需加载的指令、知识和流程提示，不是权限 |
| Grant | 对主体、动作、资源和约束的授权 |
| Workflow | 可选的确定性多阶段编排，不等于 Agent Loop |

特别注意：BearAgent 不使用 Task、Job、Thread 或 Turn 代替 Run，也不使用 Capability 同时表达
业务流程和安全权限。
