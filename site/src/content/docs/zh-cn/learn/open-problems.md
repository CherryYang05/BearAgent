---
title: Agent 仍然难在哪里
description: 从长任务、上下文、评测、安全、权限、恢复和多 Agent 协作理解工业界与学术界的研究热点。
bearStatus: concept
sourceRefs:
  - AI Agents in Depth Chapter 2
  - AI Agents in Depth Chapter 7
  - tau-bench
  - AgentDojo
  - AI Agents That Matter
  - Anthropic context engineering
  - Anthropic agent evals
---

模型在单步问题上更强，不会自动消除 Agent 的系统问题。一个十步任务只要每一步都有小概率走错，
最终成功率就会快速下降；如果其中包含发邮件、改数据库或写文件，错误还可能产生真实后果。

下面这些问题既是工业界建设 Agent 平台的难点，也是当前学术研究和 benchmark 集中的方向。

## 1. 长任务怎样保持方向和进度

短任务失败可以重来，长任务通常不能把所有步骤从头重复。系统需要知道：哪些子目标已经完成，哪些
结果已验证，下一步依据是什么，Context 即将耗尽时怎样把进度交给新的模型调用。

研究热点包括长程规划、分层任务分解、反思和错误修正、跨 Context handoff，以及能否从环境反馈中
稳定更新计划。工业界更关心可恢复进度、明确退出条件和失败时的人类接管。

BearAgent 的取舍是把“执行事实”和“下一次模型看到的 Context”分开。Event 负责保留事实，
ContextBuilder 从已提交 Event 挑选下一次决策需要的信息。当前这条 P1 路径已实现；长任务恢复尚未
实现。

## 2. Context 不是越长越好，Memory 也不是多存就好

Context 是有限注意力资源。加入更多历史、检索结果和 Tool output 会增加成本，也可能让关键规则被
淹没。Context engineering 因而研究如何选择高信号内容、压缩旧信息、按需检索、设计清晰 Tool
结果，并在多个调用之间维护目标。

Memory 进一步带来源、时效和冲突问题：旧信息何时过期？用户能否删除？两个记忆冲突时信谁？摘要
是否还能回到原始证据？把所有聊天记录放进向量库并不能自动解决这些问题。

BearAgent 当前没有 Memory，也不把 Event log 叫 Memory。前者服务未来检索，后者保留已经发生的
执行事实。

## 3. Agent 怎样被真实地评测

最终答案“看起来不错”不能说明执行过程可靠。Agent eval 至少要区分：

- outcome：最终文件、数据库或环境状态是否正确；
- trajectory：使用了哪些 Tool、参数和步骤，是否出现危险绕路；
- consistency：同一任务重复运行能否稳定成功；
- efficiency：token、延迟、费用和 Tool 次数；
- safety：面对恶意输入、越权诱导和故障时是否保持边界。

[τ-bench](https://arxiv.org/abs/2406.12045)把用户交互、领域 Policy、API Tool 和最终数据库状态放在
同一评测中，并用多次试验观察一致性。[AI Agents That Matter](https://arxiv.org/abs/2407.01502)
则指出只追准确率会忽略成本、复现、holdout 和 benchmark 过拟合。

学术界正在扩展更真实、动态、有对抗性的环境；工业界则需要把能力 eval、回归 eval、代码检查、
模型评分和人工 review 组合起来。BearAgent P1 已有五个版本化固定任务、执行路径断言和安全测试，
并以 DeepSeek V4 suite v1.1.1 完成一次真实 5/5 gate；恢复故障演练和跨版本评测体系尚未完成。

## 4. Tool 让 Agent 有用，也扩大了攻击面

Agent 会把文件、网页、邮件和 API 返回值放进 Context。这些数据可能包含 Prompt Injection，诱导
模型泄漏信息或调用危险 Tool。[AgentDojo](https://arxiv.org/abs/2406.13352)专门用不受信任 Tool 数据
测试攻击与防御，说明单靠 Prompt 无法建立可靠权限边界。

安全研究热点包括：

- 间接 Prompt Injection 的检测和隔离；
- Tool 参数的数据流与信息流控制；
- 最小权限、用户意图绑定和敏感动作确认；
- 浏览器、代码和电脑操作的 sandbox；
- Tool result 的来源、完整性与数据泄漏防护。

BearAgent 把 Model output 和 Tool output 都当作不受信任数据。当前固定 Policy 能在统一 Executor
前拒绝未允许 Tool；用户 Approval、持久 Grant 和真正的 sandbox 尚未实现。

## 5. 超时或崩溃后，外部动作到底发生了吗

对纯读取，失败后再试通常比较安全。对“发送邮件”“扣款”“写文件”，timeout 只说明调用方没收到
结果，不说明外部动作没有发生。此时盲目重试可能重复副作用，直接标记成功又可能撒谎。

工业系统需要 idempotency key、receipt、reconcile 查询和明确 `UNKNOWN` 状态。学术研究也开始把
执行环境、长期交互和可恢复状态纳入 Agent benchmark。

BearAgent 当前 ToolExecutor 遇到 timeout 只调用 Tool 一次，不自动重试。P2 才会实现 Attempt、
Checkpoint、恢复决定和 `UNKNOWN` 处置。

## 6. 自主性和人类控制怎样配合

“Agent 越自主越好”不是合理目标。低风险、可撤销、容易验证的动作可以自动完成；高影响、难撤销
或意图不清楚的动作应缩小权限、要求确认或交还给人。

真正困难的地方在于确认什么：不是笼统问“允许 Agent 吗”，而是把 Run、Tool、规范化参数、资源、
有效期和一次性使用绑定在一起。确认后的参数如果变化，旧确认应失效。

工业界关注 human-in-the-loop 的交互和审计；学术界关注可控性、校准、不确定性表达和人机协作。
BearAgent 计划在后续阶段实现这一层，当前固定 allowlist 不能代表用户 Approval。

## 7. 成本和延迟决定 Agent 能否长期使用

Agent Loop 会反复调用模型和 Tool。增加规划、评审、多个 Agent 或更长 Context 可能提高某些任务的
成功率，也会放大 token、延迟和费用。最复杂的系统不一定拥有最好的“每元成功率”。

研究热点包括模型路由、缓存、Context 压缩、早停、推理预算和成本感知评测。工业实践通常先用一个
强模型建立质量基线，再判断哪些步骤可以换成更小模型或确定性代码。

BearAgent 已把模型次数、Tool 次数、token、微美元费用和总时间作为五个独立预算维度，并在
AgentLoop 与固定任务中记账；真正的运行成本优化仍需要真实模型证据和跨版本 eval。

## 8. 多 Agent 是解决方案，还是新的协调问题

多个 Agent 可以分工、并行或互相审查，但也会带来更多 Context handoff、重复工作、冲突决定、权限
传播和评测困难。很多任务用一个 Agent 加清晰 Tool 就足够；只有单 Agent 在职责或 Context 上出现
可测瓶颈时，才值得增加协调层。

学术界研究通信协议、角色分工、协作/竞争、群体涌现和多 Agent benchmark。工业界还在推进 Tool 与
Agent 互操作规范，例如 MCP 和 A2A，但协议解决“怎样连接”，不能自动解决具体请求的权限和恢复。

BearAgent 在早期固定为单 Agent、单用户、单进程。多个 Agent 属于更晚的需求驱动扩展，不会抢在
单 Agent 的记录、失败和权限闭环之前。

## BearAgent 选择先解决哪一部分

```text
P1 已做：有界数据 → Event 与状态 → SQLite 原子保存 → 模型边界 → Tool 与 Policy
       → 文件 Tool → ContextBuilder 与 Loop → CLI 与固定任务
之后：恢复与 UNKNOWN → Approval 与 sandbox → 日常扩展 → 持续评测
```

这个顺序不是认为规划、Memory 或多 Agent 不重要，而是认为这些能力必须建立在可观察、可停止、
可恢复和不越权的 Runtime 上。更多论文、规范和项目对照见[参考资料](/zh-cn/reference/sources/)。
