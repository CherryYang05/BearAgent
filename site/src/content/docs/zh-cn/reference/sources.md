---
title: 资料来源
description: BearAgent 公共文档采用的理论、产品和工程参考资料。
bearStatus: concept
sourceRefs:
  - AI Agents in Depth
  - DeepTutor
  - Proma
  - Manus
  - CodeWhale
  - Claude Code snapshot
  - Claw Code
  - LangGraph
  - Pydantic AI
  - Inspect
  - E2B
  - MCP
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

## 产品定位与实现对照

- [DeepTutor 文档](https://docs.deeptutor.info/zh-cn/)
- [DeepTutor 官方仓库](https://github.com/HKUDS/DeepTutor)
- [DeepTutor 论文](https://arxiv.org/abs/2604.26962)
- [Proma 官方仓库](https://github.com/proma-ai/Proma)
- [Proma 产品站](https://proma.cool/)
- [Manus Sandbox](https://manus.im/blog/manus-sandbox)
- [Manus Context Engineering](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [CodeWhale 官方仓库](https://github.com/Hmbown/CodeWhale)
- [CodeWhale Authorization Order](https://github.com/Hmbown/CodeWhale/blob/main/docs/AUTHORIZATION_ORDER.md)
- [CodeWhale SQLite persistence RFC](https://github.com/Hmbown/CodeWhale/blob/main/docs/rfcs/2189-persistence-sqlite.md)
- [Cloud-code 2.1.88 extracted study repository](https://github.com/Janlaywss/cloud-code)
- [Claude Code 2.1.88 source-map snapshot](https://github.com/Rito-w/claude-code)
- [Claw Code 官方仓库](https://github.com/ultraworkers/claw-code)
- [Claw Code Philosophy](https://github.com/ultraworkers/claw-code/blob/main/PHILOSOPHY.md)

DeepTutor 的“从哪里开始”把快速上手、产品探索和 CLI 分成不同入口；BearAgent 借鉴这种面向
不同读者的导航方式，但不复制其教学产品、渠道或多 Agent 范围。

Proma 用 local-first 桌面工作区承载 Provider、Skill、MCP 与会话体验；Manus 把任务放进隔离
计算机并使用文件系统作为外部上下文；CodeWhale 更接近 Coding Agent 的多模型控制面。它们优化
的产品层不同，不能只比较 Agent Loop 或功能数量。

公开的两个 `cloud-code` / `claude-code` 仓库围绕同一 2.1.88 source-map 提取快照，
不是两个独立 Agent；Claw Code 明确是 Rust 重实现。BearAgent 只把这些仓库当作代码阅读、权限
体验和兼容性工程样本，不把非官方快照当作上游依赖或当前产品事实。

### 维护状态快照（2026-08-11）

| 参考 | 当前性质 | 使用方式 |
|---|---|---|
| Proma | 活跃的通用 Agent 桌面产品仓库，README 持续记录 2026 产品与运行时变化 | 参考 local-first 工作区、集成边界和产品体验 |
| DeepTutor | 活跃的垂直教育 Agent，2026-07 仍有 v1.5 系列发布 | 参考 Capability/Tool 分层、Memory、评测与多用户演进 |
| CodeWhale | 活跃的 Coding Agent harness，2026-07 仍有 v0.9 系列发布 | 参考授权优先级、控制面与工程证据，同时审视多状态介质的一致性成本 |
| Claude Code snapshots | 非 Anthropic 官方上游的研究/学习快照，内容固定在 2.1.88 附近 | 只用于代码阅读和行为对照，不推断当前 Claude Code 产品状态 |
| Claw Code | 活跃但自我定位为 agent-managed museum exhibit 的 Rust 重实现 | 参考 parity 与机器可读验证，不作为生产成熟度基准 |
| Manus | 官方产品文章，不是本次开源仓库样本 | 只引用 sandbox 与 context engineering 的公开设计说明 |

维护状态只说明资料是否仍适合当前对照，不代表质量背书。后续引用这些项目的新结论时要重新核验。

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

## AI Infra 专题资料

- [LangGraph 概览](https://docs.langchain.com/oss/python/langgraph/overview)与
  [持久化文档](https://docs.langchain.com/oss/python/langgraph/persistence)：用于比较持久执行、Checkpoint 和人工介入；这些能力本身不是 BearAgent 的独占卖点。
- [Pydantic AI 概览](https://pydantic.dev/docs/ai/overview/)与
  [Pydantic Evals](https://pydantic.dev/docs/ai/evals/evals/)：参考类型化 Agent 边界、OpenTelemetry 和基于执行路径的代码化评测。
- [Inspect 官方文档](https://inspect.aisi.org.uk/)：参考 Agent 任务、限制、工具路径和隔离环境评测；是否接入由 P5 Feature 决定。
- [E2B 官方文档](https://www.e2b.dev/docs)：参考远程隔离环境接口；BearAgent P3 先定义可替换的 SandboxBackend，不把托管服务变成内核依赖。
- [MCP 授权规范](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)：用于理解 HTTP 传输层授权。它不能替代 BearAgent 对具体 ToolRequest 的 Grant 和 Policy 检查。

用户提供的 AI Infra 调研报告用于发现上述主题；本页只保留可公开核验的一手资料作为工程引用。

GitHub star 只用于发现具有广泛社区关注的项目。是否采用某项设计，仍要比较 BearAgent 的
local-first、单用户、单进程范围以及失败、安全和维护成本。

## 使用原则

- 通用概念尽量链接到原始章节，不大段复制正文。
- 架构图优先根据 BearAgent 自己的边界重新绘制。
- BearAgent 当前能力只引用仓库内已经验收的 Feature 和测试。
- 规划能力必须显式标为“设计”或“规划中”。
- 技术结论优先引用论文、规范、官方文档和官方仓库；二手文章只作为补充线索。
- 引用外部实现时说明借鉴点与不采用的范围，不用 star 数或宣传文案代替设计论证。
