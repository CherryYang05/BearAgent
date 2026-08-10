---
title: 阶段与里程碑
description: BearAgent 各 P 阶段的当前结果、学习闭环和开发者交付门槛。
bearStatus: mixed
sourceRefs:
  - roadmap
  - F-0000
  - F-0001
  - F-0015
---

本页把 Roadmap 转换为可学习、可验证的阶段结果。未来计划不会因为出现在这里就变成当前能力。

## 当前阶段

| 阶段 | 状态 | 初学者可以学到 | 开发者可以验证 |
|---|---|---|---|
| P0 工程基线 | 已完成 | Agent Runtime 的边界与项目术语 | 包结构、CLI doctor、质量工具和文档治理 |
| P1 Minimum Useful Agent | 进行中 | 从领域契约走向有界模型/工具循环 | F-0001 schema；其余 Runtime Feature 尚未实现 |
| P2 Durable Runtime | 未开始 | Checkpoint、恢复、幂等与 `UNKNOWN` | 故障注入与安全边界恢复 |
| P3 Secure Self-hosted Beta | 未开始 | Grant、Approval、Sandbox 与自托管 | 安全测试、runner、备份和服务器演练 |

## 阶段什么时候可以关闭

除了 Roadmap 自己的验收标准，每个阶段还必须完成三类文档交付：

- 学习闭环：相关 Feature 已经在初学者路径中形成连续知识层次；
- 开发闭环：真实入口、架构边界、失败语义和验证命令有开发者导读；
- 事实闭环：当前状态、已知限制和下一阶段边界与代码、测试、Spec 一致。

P1 完成时会在这里补充真实 CLI 文件任务的完整学习与开发者路径，然后才开始服务器文档部署。
