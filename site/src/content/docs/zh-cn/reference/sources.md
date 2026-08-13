---
title: 参考资料怎样使用
description: BearAgent 使用哪些一手资料，以及为什么参考项目不能证明 BearAgent 的当前能力。
bearStatus: concept
sourceRefs:
  - AI Agents in Depth
  - DeepTutor
  - Proma
  - Manus
  - LangGraph
  - Pydantic AI
  - Inspect
  - E2B
  - MCP
---

外部资料帮助 BearAgent 发现问题、学习解释方式和比较方案。BearAgent 的当前行为只由本仓库的
Spec、代码、测试和验收结果确认。参考项目有某个功能，不能推导出 BearAgent 已经支持它。

## Agent 原理

- [《深入理解 AI Agent》](https://bojieli.github.io/ai-agent-book/)：模型、上下文、工具、Memory 与评测的系统介绍；
- [第 1 章：Agent 基础知识](https://bojieli.github.io/ai-agent-book/book/chapter1/)；
- [第 2 章：上下文工程](https://bojieli.github.io/ai-agent-book/book/chapter2/)；
- [第 4 章：工具](https://bojieli.github.io/ai-agent-book/book/chapter4/)；
- [第 6 章：Agent 的评估](https://bojieli.github.io/ai-agent-book/book/chapter6/)。

## 产品和架构对照

- [DeepTutor 官方仓库](https://github.com/HKUDS/DeepTutor)与[中文文档](https://docs.deeptutor.info/zh-cn/)：学习面向不同读者的导航，以及垂直 Agent 的任务组织；
- [Proma 官方仓库](https://github.com/proma-ai/Proma)：观察 local-first 工作区、Provider、Skill 和 MCP 的产品连接；
- [Manus Sandbox](https://manus.im/blog/manus-sandbox)与[上下文工程](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)：比较隔离环境和长任务上下文管理；
- [CodeWhale 授权顺序](https://github.com/Hmbown/CodeWhale/blob/main/docs/AUTHORIZATION_ORDER.md)：对照编码 Agent 的授权路径；
- [OpenHands SDK 架构](https://docs.openhands.dev/sdk/arch/sdk)：对照 Agent Loop、Workspace、Tool 和 Runtime/Sandbox 的分工。

## Runtime、评测和基础设施

- [LangGraph 持久化](https://docs.langchain.com/oss/python/langgraph/persistence)：比较持久状态、Checkpoint 和人工介入；
- [Pydantic AI](https://pydantic.dev/docs/ai/overview/)与[Pydantic Evals](https://pydantic.dev/docs/ai/evals/evals/)：参考类型边界、追踪和代码化评测；
- [Inspect](https://inspect.aisi.org.uk/)：参考任务、工具路径和隔离环境评测；
- [E2B](https://www.e2b.dev/docs)：参考远程隔离执行接口；
- [MCP 授权规范](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)：理解传输层授权，但它不能替代 BearAgent 对具体 ToolRequest 的权限判断。

## 选择和维护资料的规则

优先引用论文、规范、官方文档和官方仓库。GitHub star 只帮助发现受关注的项目，不说明设计适合
BearAgent。引用资料时写清借鉴了什么、没有采用什么，并在形成新技术结论前重新核验维护状态。
