---
title: "Feature: <name>"
status: draft
spec_id: F-NNNN
milestone: P<n>
owner: <name>
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
implemented_in: null
related_adrs: []
---

# F-NNNN：<用用户或系统行为描述功能>

Filename: `docs/specs/F-NNNN-<slug>.md`

## 1. 为什么现在要做

先写一个具体场景：谁在什么情况下遇到什么问题？仓库中有哪些证据说明问题确实存在？

## 2. 本次交付

- G-1:

## 3. 本次不做

- NG-1:

## 4. 需要先说明的约定

只解释本功能新出现的名词。先给例子，再给定义；已经在架构术语表中的词不重复改名。

## 5. 使用场景

### Scenario A

用自然语言写清前提、动作和可观察结果；需要严格验收时再补 Given / When / Then。

## 6. 必须满足的行为

- FR-1:
- FR-2:

## 7. 对外入口和模块连接

CLI、API、Tool、Event、配置或 Python 接口有什么变化？同时说明谁调用它、结果交给谁。没有变化则写“无”。

## 8. 状态和保存的数据

说明状态怎样变化、哪些事实会保存、旧数据怎样继续读取。没有持久化则明确写出。

## 9. 失败时会发生什么

分别说明超时、重试、取消、进程中断、部分成功和 `UNKNOWN`。不要只列名词；写清用户最终看到的状态。

## 10. 安全与隐私

权限、信任边界、secrets、输入校验、资源限制。

## 11. 怎样检查执行过程

用户或开发者需要看到哪些 Event、日志、trace、指标和审计信息？

## 12. 上线与回退

本地/服务器启用顺序、feature flag、迁移与回退。

## 13. 验收标准

- AC-1: 可执行且二值判断的标准。
- AC-2:

## 14. 验证方式

- Unit:
- Contract:
- Integration:
- Recovery:
- Security:
- Eval/manual:

## 15. 文档同步

- [ ] Engineering source of truth (`docs/`)
- [ ] Site beginner learning path
- [ ] Site developer documentation
- [ ] Site current status / milestone summary
- [ ] Architecture / ADR
- [ ] Deployment docs
- [ ] Generated reference

每个 Feature 都要检查以上三个 `site/` 入口。不需要新文章时，写出准备更新的现有页面。

## 16. 尚未决定的问题

- OQ-1:
