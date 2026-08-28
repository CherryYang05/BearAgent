---
title: "Feature: <name>"
status: draft
spec_id: F-NNNN
milestone: P<n>
change_level: S1
owner: <name>
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
implemented_in: null
related_adrs: []
---

# F-NNNN：<用用户或系统行为描述功能>

Filename: `docs/specs/F-NNNN-<slug>.md`

S1 写完核心部分即可；不适用的条件部分直接写 `N/A` 和原因。S2 必须展开状态、失败恢复、安全、
迁移与回退，并创建 ADR 和 Plan。不要为了填模板复制代码结构或生成完整类/函数清单。

## 1. 问题与证据（S1/S2）

谁在什么情况下遇到什么问题？仓库中有哪些代码、测试、日志或用户路径说明问题确实存在？

## 2. 目标与非目标（S1/S2）

### 本次交付

- G-1:

### 本次不做

- NG-1:

## 3. 场景与可观察行为（S1/S2）

### Scenario A

写清前提、动作和用户或调用方看到的结果。只有需要严格验收时才补 Given / When / Then。

- FR-1:
- FR-2:

## 4. 对外入口与模块连接（S1/S2）

CLI、API、Tool、Event、配置或 Python 接口有什么变化？谁调用它，结果交给谁？没有变化则写 `N/A`
和原因。

## 5. 状态与持久化（S2；S1 按需）

说明状态转换、保存的事实、兼容读取、migration 和 projection。没有状态或持久化变化时写 `N/A`。

## 6. 失败、恢复与安全边界（S1 简述；S2 完整）

写清适用的超时、取消、进程中断、部分成功、重试、`UNKNOWN`、权限、secret、输入校验和资源限制。
不要只列名词；说明失败后用户看到什么，以及系统可以或不可以继续做什么。

## 7. 上线与回退（S2；S1 按需）

说明启用顺序、兼容窗口、feature flag、migration 和可执行回退。没有上线动作时写 `N/A`。

## 8. 验收标准与证据（S1/S2）

每个标准必须能够二值判断，并映射到具体测试、脚本、报告或人工演练。

| AC | 可判断的结果 | 证据路径或命令 |
|---|---|---|
| AC-1 |  |  |
| AC-2 |  |  |

## 9. 文档影响（S1/S2）

每个表面都必须判断，但不要求每个表面都发生修改。没有影响时写 `N/A` 和具体原因。

| 表面 | 更新路径，或 `N/A` + 原因 |
|---|---|
| Engineering `docs/` |  |
| Site beginner path |  |
| Site developer docs |  |
| Site current status |  |
| Generated reference |  |

## 10. 尚未决定的问题（S1/S2）

- OQ-1:
