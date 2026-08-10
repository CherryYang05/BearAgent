---
title: 资料来源
description: BearAgent 公共文档采用的理论、产品和工程参考资料。
bearStatus: concept
sourceRefs:
  - AI Agents in Depth
  - DeepTutor
  - Proma
  - LangGraph
  - AutoGen
  - OpenHands
  - Dify
---

BearAgent 文档会消化并重新组织外部资料，再用本项目的 Spec、ADR、代码和测试验证具体实现。
外部项目拥有某项功能，不代表 BearAgent 当前也支持。

## Agent 原理

- [《深入理解 AI Agent》](https://bojieli.github.io/ai-agent-book/)
- [第 1 章：Agent 基础知识](https://bojieli.github.io/ai-agent-book/book/chapter1/)
- [第 2 章：上下文工程](https://bojieli.github.io/ai-agent-book/book/chapter2/)
- [第 3 章：用户记忆和知识库](https://bojieli.github.io/ai-agent-book/book/chapter3/)
- [第 4 章：工具](https://bojieli.github.io/ai-agent-book/book/chapter4/)
- [第 6 章：Agent 的评估](https://bojieli.github.io/ai-agent-book/book/chapter6/)
- [第 8 章：Agent 的持续进化](https://bojieli.github.io/ai-agent-book/book/chapter8/)

## 文档与产品表达

- [DeepTutor 文档](https://docs.deeptutor.info/zh-cn/)
- [Proma](https://proma.cool/)

DeepTutor 的“从哪里开始”把快速上手、产品探索和 CLI 分成不同入口；BearAgent 借鉴这种面向
不同读者的导航方式，但不复制其教学产品、渠道或多 Agent 范围。

## 高关注 Agent 项目的官方资料

这些项目用于专题对照和发现问题，不作为 BearAgent 当前能力的证据：

- [LangGraph 官方仓库](https://github.com/langchain-ai/langgraph)与
  [Persistence 文档](https://docs.langchain.com/oss/python/langgraph/persistence)：参考持久状态、Checkpoint 和恢复的概念对照。
- [Microsoft AutoGen 官方仓库](https://github.com/microsoft/autogen)与
  [Core 文档](https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/)：参考分层 API、消息和 Agent Runtime；使用时同时关注其当前维护状态。
- [OpenHands 官方仓库](https://github.com/All-Hands-AI/OpenHands)与
  [SDK 架构](https://docs.openhands.dev/sdk/arch/sdk)：参考 Agent Loop、Workspace、Tool 与 Runtime/Sandbox 的职责拆分。
- [Dify 官方仓库](https://github.com/langgenius/dify)与
  [官方文档](https://docs.dify.ai/)：参考工作流、运行观察和面向使用者的文档组织。

GitHub star 只用于发现具有广泛社区关注的项目。是否采用某项设计，仍要比较 BearAgent 的
local-first、单用户、单进程范围以及失败、安全和维护成本。

## 使用原则

- 通用概念尽量链接到原始章节，不大段复制正文。
- 架构图优先根据 BearAgent 自己的边界重新绘制。
- BearAgent 当前能力只引用仓库内已经验收的 Feature 和测试。
- 规划能力必须显式标为“设计”或“规划中”。
- 技术结论优先引用论文、规范、官方文档和官方仓库；二手文章只作为补充线索。
- 引用外部实现时说明借鉴点与不采用的范围，不用 star 数或宣传文案代替设计论证。
