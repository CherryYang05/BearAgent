---
title: "ADR-0005: No model-generated shell in the host runtime"
status: accepted
date: 2026-08-09
---

# ADR-0005：Host runtime 不执行模型生成 shell

## Context

在 API/runtime 进程执行模型生成命令会同时暴露宿主文件、服务数据、provider secrets 和网络权限；字符串过滤不能构成可靠隔离。

## Decision

P1/P2 不提供 shell。P3 通过 `SandboxBackend` 调用独立、无特权、受资源限制、默认断网且不挂 secrets 的 runner。runner 不可用时 shell tool 不注册，不回退到 host subprocess。

## Alternatives

- host subprocess + allowlist：实现快，但 shell 解析、二进制间接执行、文件和 secret 范围难以控制。
- 主 API 容器内执行：比宿主略好，但仍与数据库、key 和服务生命周期共享边界。
- 每任务完整 VM：隔离更强，但个人服务器初期资源和实现成本过高。

## Consequences

- P1 能力刻意受限；P3 需要 runner RPC、workspace 传递和清理逻辑。
- 后续可以添加 Docker/rootless Podman/remote runner adapter，而不改变 runtime 契约。
