---
title: "Implementation Plan: <feature>"
status: draft
plan_id: PLAN-F-NNNN
related_spec: F-NNNN
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
---

# PLAN-F-NNNN：<功能名称>

关联 Spec：`docs/specs/F-NNNN-<name>.md`

S2 必须创建 Plan。S1 只有在需要多个独立验证切片、跨多个提交/PR，或无法作为一个连贯变更安全
评审时才创建 Plan。Plan 不重复 Spec 的需求，也不维护完整文件清单。

## 开始前确认

- [ ] Spec status is `accepted`.
- [ ] 影响实现的开放问题已经解决。
- [ ] S2 的 ADR 已接受，迁移/回退边界已经明确。

## 实施步骤

### 第 1 步：<完成后能单独验证的结果>

- 状态：pending；
- 交付结果：
- 代码落点：
- 接入关系：谁调用它，结果交给谁。
- 重点测试：
- 验证命令：
- 回退方式：

### 第 2 步：<完成后能单独验证的结果>

- 状态：pending；
- 交付结果：
- 代码落点：
- 接入关系：
- 重点测试：
- 验证命令：
- 回退方式：

## 跨切片检查

不适用的项目写 `N/A` 和原因；Plan 变为 `completed` 前不能保留未处理项。

| 风险面 | 结果或 `N/A` + 原因 | 证据 |
|---|---|---|
| Persistence / recovery |  |  |
| Permission / security |  |  |
| Timeout / cancel / limits |  |  |
| Migration / rollback |  |  |
| Logs / trace / metrics |  |  |
| Documentation impact |  |  |

## 最终验证

列出实际运行的命令和结果，包括 `uv run python scripts/check_governance.py`。站点受到影响时再运行
`npm run build --prefix=site`。命令没有实际通过前，不得把 Plan 标记为 `completed`。
