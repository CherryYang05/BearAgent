---
title: "ADR-0005: The host Runtime never executes model-generated shell"
status: accepted
date: 2026-08-09
---

# ADR-0005：主 Runtime 进程不执行模型生成的 shell

## 要解决的问题

主 Runtime 进程拥有 Provider 密钥、数据库和宿主文件权限。在这里执行模型生成的命令，会把这些
资源同时暴露给不可信代码；字符串过滤和简单 allowlist 不能形成可靠隔离。

## 决定

P1 和 P2 不提供 shell。P3 通过 `SandboxBackend` 调用独立、无特权、受资源限制、默认断网且不
挂载密钥的 runner。runner 不可用时 shell Tool 不注册，绝不回退到 host subprocess。

## 比较过的方案

- host subprocess + allowlist 无法覆盖 shell 解析、间接二进制和文件权限；
- 在主 API 容器中执行仍共享数据库、密钥和服务生命周期；
- 每任务完整 VM 隔离更强，但超出个人服务器第一版的资源与维护范围。

## 怎样验证

测试 runner 读不到 Provider key、主数据库、宿主根目录、用户 home 和 Docker socket；资源、网络、
输出和执行时间都必须有上限。runner 故障时验证没有 host fallback。
