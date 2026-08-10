# BearAgent 文档

BearAgent 的目标是构建一个面向长任务的个人 Agent Runtime：小而完整、可恢复、可审计，并可以从本地平滑迁移到自托管服务器。

公开站点位于 [`site/`](../site/README.md)，同时维护初学者学习路径和开发者文档；P1 期间只在本地预览和构建。本目录继续作为工程设计与项目治理的 Source of Truth，站点内容必须从这里、代码和测试派生。

## 阅读顺序

1. [总体架构](architecture/overview.md)：项目边界、核心对象、状态机、事件、工具、权限、持久化和安全设计。
2. [AI 辅助开发 SOP](development/ai-development-sop.md)：如何让 ChatGPT/Codex 参与需求、设计、实现、测试和文档同步。
3. [路线图](project/roadmap.md)：为什么做、每个阶段做什么、何时算完成。
4. [Feature Specs](specs/README.md)：每个阶段有哪些功能，以及各功能的需求和状态。
5. [Implementation Plans](plans/README.md)：当前 Feature 做到哪个可验证切片。
6. [部署策略](deployment/self-hosting.md)：何时本地运行，何时上服务器，如何通过 1Panel 和子域名发布。

## 文档的权威层级

```text
用户可观察行为：验收测试 + Feature Spec
跨模块决策：ADR
当前系统结构：Architecture 文档
当前阶段：Roadmap
当前实现切片：Implementation Plan + 代码和测试
开发约束：AGENTS.md
实现细节：代码、类型和迁移文件
未来意图：Roadmap
聊天记录：仅作讨论材料，不是 Source of Truth
```

发生冲突时，先判断文档描述的是“当前事实”还是“未来计划”。Roadmap 不得覆盖已验收的行为；聊天结论只有进入 Spec/ADR 并提交 Git 后才生效。

## 文档状态

文档使用以下状态：

- `draft`：讨论中，不授权实现。
- `accepted`：可以作为实现依据。
- `implemented`：实现和验收测试已完成。
- `superseded`：被新的 Spec/ADR 替代，保留历史。

架构文档只描述当前基线和已经接受的目标边界；尚未决定的方案必须明确标为“开放问题”。

Feature ID 在全项目内稳定递增；所属阶段由 Feature Spec 的 `milestone: P<n>` 声明。阶段调整只修改 `milestone`，不重命名 `F-NNNN`。
