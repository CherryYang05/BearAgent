---
title: "ADR-0006: P0 only adds dependencies needed for the engineering baseline"
status: accepted
date: 2026-08-09
---

# ADR-0006：P0 只引入建立工程基线所需的依赖

## 要解决的问题

P0 要建立可复现安装、CLI、测试、静态检查和 CI。一次性加入 P1 至 P3 的全部依赖，会在没有真实
用例时提前锁定设计，也会让最小运行环境变重。

## 决定

- Python 固定为 `>=3.12,<3.13`，使用 uv 管理环境、依赖组和 lockfile；
- 使用 hatchling 构建 `src` layout package；
- P0 唯一直接运行时依赖是 Typer，用于 CLI；
- Ruff、Pyright 和 pytest 只在开发依赖组；
- 文档链接和 import boundary 使用仓库脚本或 pytest；
- Pydantic、aiosqlite、httpx、FastAPI 等在实际 Feature 需要时再引入。

## 带来的影响

P0 安装和 CI 保持很小，每个新增生产依赖都有明确理由。使用 BearAgent 需要 uv 管理的 Python 3.12；
系统 Python 3.14 不能直接代替。

## 怎样验证

lockfile、Windows/Ubuntu CI、CLI 启动和完整质量检查必须从干净环境通过。新增生产依赖时，Spec 或
ADR 要说明它解决的具体问题。
