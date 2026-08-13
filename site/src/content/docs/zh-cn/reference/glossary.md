---
title: 术语表
description: BearAgent 中稳定使用的核心项目术语及其白话解释。
bearStatus: design
sourceRefs:
  - architecture/overview
---

这些术语来自 BearAgent 已接受的架构。文档第一次使用英文术语时应同时给出中文解释；代码标识
保持原名，便于读者搜索源码。

| 术语 | 定义 |
|---|---|
| Agent | 使用模型、工具和策略完成目标的配置，不是一次执行 |
| Session | 用户连续对话的容器，可以包含多个 Run |
| Run | 对一条用户请求的一次可持久化执行 |
| Activity | 一个需要跟踪生命周期的模型调用或工具调用 |
| Event | 已经发生、不可变、带顺序的事实 |
| Command | 希望系统执行的动作，可以被拒绝 |
| Port（内部接口） | 核心代码规定“需要什么能力”的接口，不绑定某个外部产品或技术 |
| Adapter（适配器） | 把数据库、模型 SDK 等外部实现翻译并接到内部接口的代码 |
| Schema（数据格式） | 数据有哪些字段、字段类型和校验规则；JSON Schema 是这种规则的机器可读版本 |
| Checkpoint | 某个 Event sequence 上的派生状态快照，可重建 |
| Artifact | Run 生成并由用户取回的文件或结构化产物 |
| Tool | 具有输入 schema 和执行语义的动作接口 |
| Skill | 可按需加载的指令、知识和流程提示，不是权限 |
| Grant | 对主体、动作、资源和约束的授权 |
| Workflow | 可选的确定性多阶段编排，不等于 Agent Loop |

特别注意：BearAgent 不使用 Task、Job、Thread 或 Turn 代替 Run，也不使用 Capability 同时表达
业务流程和安全权限。
