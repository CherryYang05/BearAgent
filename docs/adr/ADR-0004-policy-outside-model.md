---
title: "ADR-0004: Policy is enforced outside the model"
status: accepted
date: 2026-08-09
---

# ADR-0004：权限策略位于模型之外

## Context

Prompt injection、模型错误和恶意 Tool 输出都可能诱导 Agent 越权。自然语言要求不能构成安全边界。

## Decision

所有外部动作变成 canonical ToolRequest，并由确定性的 PolicyEngine 根据 Grant 返回 `ALLOW / ASK / DENY`。Approval 绑定 exact arguments hash 和过期时间。Prompt、Skill、模型和 Tool 输出不能授予 Grant。

## Alternatives

- 只在 system prompt 写“不要做危险操作”：无法强制，且会被间接 prompt injection 影响。
- 每次工具调用都人工批准：安全但不可用，也无法表达低风险自动化。
- Tool 自己散落权限判断：规则重复、难审计，容易出现 adapter bypass。

## Consequences

- 新 Tool 必须声明 side effect 和 required grants，并通过统一 executor。
- Policy/approval path 需要独立 security tests 和审计事件。
