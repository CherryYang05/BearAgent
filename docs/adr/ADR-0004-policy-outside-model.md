---
title: "ADR-0004: Runtime decides permissions; the model cannot grant them"
status: accepted
date: 2026-08-09
---

# ADR-0004：权限由 Runtime 判断，不由模型授予

## 要解决的问题

模型、工作区文件和工具输出都可能包含错误或恶意指令。只在 Prompt 中要求“不要做危险操作”，
无法阻止模型请求越权路径或被间接 Prompt injection 诱导。

## 决定

所有外部动作先转换成规范化的 `ToolRequest`。`PolicyEngine` 根据已有 Grant 返回 `ALLOW`、`ASK`
或 `DENY`。需要用户批准时，Approval 绑定精确参数的 hash 和有效期。

Prompt、Skill、模型输出、工具输出和工作区文件都不能创建或扩大 Grant。所有 Tool 必须经过同一个
执行入口，adapter 不得绕过 Policy。

## 为什么不选其他方案

- System Prompt 无法强制执行安全规则；
- 所有工具调用都人工批准会使低风险自动化无法使用；
- 每个 Tool 自己检查权限会产生重复规则和绕过路径。

## 怎样验证

安全测试必须覆盖默认拒绝、路径规范化、批准参数篡改、过期和重放、跨 Run 使用，以及模型或工具
内容尝试增加权限。批准 `write_file(a.txt)` 后修改任一关键参数，旧批准必须失效。
