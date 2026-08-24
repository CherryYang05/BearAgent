---
title: 参考资料与阅读路线
description: BearAgent 用哪些书籍、论文、规范和官方工程资料理解 Agent，以及每份资料适合回答什么问题。
bearStatus: concept
sourceRefs:
  - AI Agents in Depth
  - agentic-design-patterns
  - deepseek-harness
  - METR
  - OpenAI
  - Anthropic
  - tau-bench
  - AgentDojo
  - MCP
  - A2A
---

外部资料帮助我们理解 Agent 的通用问题、发现工程风险和比较方案。BearAgent 当前行为仍只由本仓库
代码、测试和可复现结果确认。参考项目支持某项能力，不能推导出 BearAgent 已经支持它。

资料按“读者想回答的问题”整理。行业发展很快，带能力数字的页面应同时查看发布日期、任务定义和
最新版本；这里记录的是截至 2026 年 8 月核对过的入口。

## 想系统学习 Agent：先读书和课程型资料

- [《深入理解 AI Agent》](https://bojieli.github.io/ai-agent-book/)：从 Model、Context、Tool、Memory
  到 eval 的系统介绍，适合作为本站学习路径的概念底图；
- [第 1 章：Agent 基础知识](https://bojieli.github.io/ai-agent-book/book/chapter1/)：区分模型、环境、
  观察和动作；
- [第 2 章：上下文工程](https://bojieli.github.io/ai-agent-book/book/chapter2/)：理解 Context 为什么是
  有限资源，以及怎样筛选信息；
- [第 4 章：工具](https://bojieli.github.io/ai-agent-book/book/chapter4/)：理解 schema、Tool use 和外部
  行动之间的关系；
- [第 7 章：Agent 的评估](https://bojieli.github.io/ai-agent-book/book/chapter7/)：从最终结果、过程和成本
  理解 eval。

读完第 1、2、4 章后，可以回到本站的[一项 Agent 任务怎样运转](/BearAgent/zh-cn/learn/agent-basics/)；第 7 章适合
和[Agent 仍然难在哪里](/BearAgent/zh-cn/learn/open-problems/)对照阅读。

- [Agentic Design Patterns 中文翻译](https://github.com/xindoo/agentic-design-patterns)：适合按 Reflection、
  Tool use、Planning、Multi-Agent 等模式建立索引。模式名称帮助比较方案，不代表每个 Agent 都需要
  同时实现这些模式。

## 想知道 Agent 现在能做到什么

- [METR Task-Completion Time Horizons](https://metr.org/time-horizons/)：按人类专家任务时长估计前沿
  Agent 在软件、机器学习和网络安全任务上的成功概率；页面持续更新，也明确说明这些任务较干净、
  不能直接换算为职业自动化；
- [TheAgentCompany](https://arxiv.org/abs/2412.14161)：在模拟软件公司的网页、代码和沟通环境中评测
  数字工作任务，适合理解简单任务与长程任务之间的差距；
- [OSWorld](https://arxiv.org/abs/2404.07972)：在真实操作系统和桌面应用中评测电脑操作，重点暴露
  GUI grounding、操作知识和跨应用流程问题；
- [GAIA](https://arxiv.org/abs/2311.12983)：需要推理、浏览、Tool 与多模态能力的通用助手 benchmark；
- [SWE-bench](https://arxiv.org/abs/2310.06770)：用真实 GitHub issue 和仓库验证编码系统是否真正修复
  问题。

Benchmark 的旧 baseline 不应当作今天的模型上限。更值得长期关注的是任务环境、验证方法、重复成功
率和失败类型。

## 想理解工业界怎样建设 Agent 系统

- [OpenAI：A practical guide to building agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)：
  从用例筛选、Model/Tool/instructions、单 Agent 到 guardrail 的工程路径；
- [Anthropic：Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)：
  区分固定 Workflow 与动态 Agent，并建议从能满足需求的简单结构开始；
- [Anthropic：Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)：
  把 Context 看成有限注意力资源，讨论 Prompt、Tool、检索和长任务信息筛选；
- [Anthropic：Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)：
  讨论跨 Context 保留进度、增量工作和交接；
- [Anthropic：Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)：
  解释 task、trial、grader、trajectory、outcome 和 harness 怎样组成可维护 eval。

这些文章是各家公司基于自身系统的工程经验，不是普适定律。本站把它们与论文、代码和 BearAgent
约束交叉阅读。

## 想研究可靠性、评测和安全

- [τ-bench](https://arxiv.org/abs/2406.12045)：同时测试用户交互、领域 Policy、API Tool 和最终数据库
  状态，并用 `pass^k` 观察多次运行的一致性；
- [AI Agents That Matter](https://arxiv.org/abs/2407.01502)：指出只追准确率会忽略成本、复现、holdout
  和 benchmark 过拟合；
- [AgentDojo](https://arxiv.org/abs/2406.13352)：用不受信任 Tool 数据、真实任务和攻击案例评测间接
  Prompt Injection；
- [Survey on Evaluation of LLM-based Agents](https://arxiv.org/abs/2503.16416)：整理规划、Tool use、
  Memory、交互、安全、成本和鲁棒性等评测维度；
- [Inspect](https://inspect.aisi.org.uk/)：官方评测框架文档，可参考 task、solver、Tool、sandbox 和
  scorer 的代码化组织；
- [Pydantic Evals](https://ai.pydantic.dev/evals/)：参考类型化 dataset、grader 和 span-based eval。

BearAgent 特别关注 outcome 与执行路径同时验证：最终报告正确并不代表中间没有越权 Tool 调用；安全
路径正确也不能替代任务质量。

## 想理解持久化、恢复与隔离

- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)：对照 thread、
  checkpoint、replay 和 human-in-the-loop 的持久状态模型；
- [OpenHands SDK architecture](https://docs.openhands.dev/sdk/arch/sdk)：对照 Agent Loop、Workspace、
  Tool 和 Runtime/Sandbox 的分工；
- [Manus Sandbox](https://manus.im/blog/manus-sandbox)：了解远程 Agent sandbox 的环境边界；
- [Manus Context Engineering](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)：
  对照长任务中的 Context 管理经验；
- [E2B documentation](https://www.e2b.dev/docs)：参考远程隔离执行接口和生命周期。

这些系统的持久化或 sandbox 方案不等于 BearAgent 会采用相同实现。BearAgent 当前只实现 SQLite Event
与 projection 的原子保存，尚未实现启动恢复和隔离 runner。

## 想理解 Tool 与 Agent 互操作

- [Model Context Protocol 规范](https://modelcontextprotocol.io/specification/2026-07-28)：理解 Host、Client、
  Server、Tool/Resource/Prompt 和授权等协议边界；
- [MCP 2026-07-28 发布说明](https://blog.modelcontextprotocol.io/posts/2026-07-28/)：了解规范版本变化和
  长运行任务等扩展方向；
- [Agent2Agent Protocol](https://a2a-protocol.org/latest/)：了解独立 Agent 之间任务、消息和 Artifact
  交换的协议目标。

协议解决“系统怎样互相描述和通信”，不能替代本地 Runtime 对具体 ToolRequest 的 Policy、timeout、
Event 和恢复处理。BearAgent 当前未接入 MCP 或 A2A。

## 想看不同产品怎样组织文档和代码

- [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)：其开发者文档把快速开始、架构、
  生命周期、能力边界、防御性模式和测试分开，适合参考“教程与工程参考各负其责”的组织方式；
- [DeepTutor 官方仓库](https://github.com/HKUDS/DeepTutor)与
  [中文文档](https://docs.deeptutor.info/zh-cn/)：观察垂直 Agent 的任务组织和面向不同读者的导航；
- [Proma 官方仓库](https://github.com/proma-ai/Proma)：观察 local-first 工作区、Provider、Skill 和 MCP
  在产品中的连接；
- [CodeWhale 授权顺序](https://github.com/Hmbown/CodeWhale/blob/main/docs/AUTHORIZATION_ORDER.md)：
  对照编码 Agent 怎样组织授权路径。

阅读参考项目时应重新核对其维护状态、文档版本和实际代码。GitHub star 只帮助发现项目，不证明设计
适合 BearAgent。

## 想理解 Python package 怎样发布和安装

- [uv：Building and publishing a package](https://docs.astral.sh/uv/guides/package/)：确认
  `uv build --no-sources`、`uv publish`、token/Trusted Publisher 和发布后隔离安装的当前用法；
- [pip install 官方文档](https://pip.pypa.io/en/stable/cli/pip_install/)：理解 pip 怎样从 PyPI、wheel、
  sdist 或本地路径解析和安装 package；
- [Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/)：
  对照 `pyproject.toml`、distribution 构建、TestPyPI 和 PyPI 发布的标准流程。

这些资料说明 Python packaging 工具怎样工作，不证明 BearAgent 已经发布。BearAgent 的实际发布版本、
PyPI 项目归属和可用 CLI 仍以项目 release 记录与[当前状态](/BearAgent/zh-cn/project/status/)为准。

## 资料进入本站的规则

1. BearAgent 行为优先引用本仓库代码、测试和当前状态；
2. 技术结论优先使用论文、规范、官方文档和官方仓库；
3. 能力数字注明任务范围和时间，不从单个 benchmark 推导通用自动化；
4. 明确区分“借鉴问题”“考虑中的方案”和“当前实现”；
5. 在形成新的架构结论前重新核验来源，不复制旧文章中的过期接口。
