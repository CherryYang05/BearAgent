---
title: "ADR-0006: P0 tooling and dependency baseline"
status: accepted
date: 2026-08-09
---

# ADR-0006：P0 工具链与依赖基线

## Context

P0 需要可复现安装、CLI、测试、静态检查和 CI。生产依赖会进入后续所有运行环境，必须保持最小。

## Decision

- 使用 `requires-python >=3.12,<3.13` 和 `.python-version` 固定 Python minor。
- 使用 uv 管理环境、dependency groups 和 lockfile。
- P0 唯一直接运行时依赖是 Typer，用于稳定 CLI 入口。
- 使用 hatchling 构建 `src` layout package。
- Ruff、Pyright、pytest 只进入 `dev` dependency group。
- 文档链接和 import boundary 检查使用项目自有 Python 脚本/pytest，不增加专用依赖。
- Pydantic、aiosqlite、httpx、FastAPI 等在真实 Feature 使用时再通过 ADR/Spec 加入。

## Alternatives

- 标准库 argparse：零依赖，但与已接受架构的 Typer 选择不一致，后续还要迁移命令结构。
- 一次加入 P1-P3 全部依赖：减少后续安装步骤，但产生未使用依赖和提前锁定设计。
- Poetry/pip-tools：可行，但项目已接受 uv，重复工具没有收益。

## Consequences

- P0 环境很小，lockfile 和 CI 快；后续每个生产依赖都有明确引入点。
- 运行 BearAgent 需要 Typer 及其依赖；CLI adapter 仍不得泄漏到 runtime core。
- Python 3.14 系统环境不能直接运行，必须使用 uv 管理的 3.12。
