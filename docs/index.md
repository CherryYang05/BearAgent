# BearAgent 工程文档

这组文档保存 BearAgent 的产品范围、技术决定、功能要求和实施记录。第一次进入仓库时，按下面的
顺序阅读即可；不需要先把所有 ADR 和 Spec 看完。

## 先读四份

1. [产品定位](project/product-positioning.md)：BearAgent 为谁解决什么问题，第一版为什么保持很小；
2. [总体架构](architecture/overview.md)：一次 Run 经过哪些模块，当前实现和后续设计怎样区分；
3. [项目路线图](project/roadmap.md)：每个阶段交付什么，怎样用真实结果关闭；
4. 当前 Feature 的 [Spec](specs/README.md)、相关 [ADR](adr/README.md) 和 [Plan](plans/README.md)。

准备参与开发时再读 [AI 辅助开发流程](development/ai-development-sop.md)。需要部署背景时读
[本地开发与自托管](deployment/self-hosting.md)。实际使用 P1 CLI 时直接读
[命令行完整使用手册](../site/src/content/docs/zh-cn/guides/cli.md)；公共学习站位于
[`site/`](../site/README.md)。

## 一件事实写在哪里

| 问题 | 以哪里为准 |
|---|---|
| 当前阶段和阶段关闭条件 | Roadmap |
| 一个 Feature 必须做到什么 | Feature Spec + 验收测试 |
| 为什么选择某个跨模块方案 | ADR |
| 当前准备按什么顺序实现 | active Implementation Plan |
| 模块现在怎样连接 | Architecture + 代码 |
| 行为是否已经成立 | 代码、测试和可复现命令 |
| 开发约束和完成标准 | `AGENTS.md` |
| 当前 CLI 怎样安装、配置和排错 | `site/.../guides/cli.md`，精确字段回到 F-0005/Schema/代码 |
| 面向读者的解释 | `site/`，内容必须能追溯到以上事实 |

聊天记录只用于讨论。一个结论只有写进仓库并通过相应审查后，才成为项目决定。

## 状态是什么意思

- `draft`：仍在讨论，不能据此实现；
- `accepted`：已经同意，可以作为实现依据；
- `implemented`：代码和验收已经完成；
- `superseded`：已被新文档替代，保留用于理解历史。

ADR 的 `accepted` 只表示决定已经生效，不表示相关 Feature 已经写完。Feature ID 全项目稳定，所属
阶段写在 Spec 的 `milestone` 中；移动阶段时不重编号。

## 写文档时

先说明具体问题或执行场景，再引入 Runtime、port、adapter、Event、Reducer 等必要术语。保留精确
术语，不用更长的人造中文短语替换它们；同时避免只有术语而没有行为说明。`docs/` 保持可验收的
准确性，`site/` 把同一事实组织成连贯的学习和代码阅读路径。
