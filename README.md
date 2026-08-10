<div align="center">

<h1>BearAgent</h1>
<p><strong>可靠、可恢复、权限明确的本地优先个人 AI Agent Runtime</strong></p>
<p><sub>A lightweight, local-first and self-hostable runtime for long-running, tool-intensive personal AI tasks.</sub></p>
<p>
  <a href="#project-status"><img alt="P1 in progress" src="https://img.shields.io/badge/status-P1%20in%20progress-2563EB"></a>
  <a href="https://www.python.org/"><img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3776AB?logo=python&amp;logoColor=white"></a>
  <a href="https://docs.astral.sh/uv/"><img alt="uv package manager" src="https://img.shields.io/badge/package%20manager-uv-DE5FE9"></a>
  <a href="https://github.com/CherryYang05/BearAgent/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/CherryYang05/BearAgent/actions/workflows/ci.yml/badge.svg"></a>
</p>
<p>
  <a href="#why-bearagent">为什么是 BearAgent</a> ·
  <a href="#architecture">架构</a> ·
  <a href="#project-status">当前状态</a> ·
  <a href="#quick-start">快速开始</a> ·
  <a href="#roadmap">路线图</a> ·
  <a href="#contributing">参与开发</a>
</p>

</div>

> [!IMPORTANT]
> BearAgent 已完成 **P0 Engineering Baseline**，当前处于 **P1 Minimum Useful Agent**。领域契约与本地文档站已经实现；真实 Model Provider、Agent Loop、文件工具和 SQLite Run 尚不可用，因此它现在还不能执行真实 Agent 任务。

## Why BearAgent

很多 Agent demo 在 happy path 上只是 `model → tool → model` 循环。一旦进程中断、外部写入结果不确定、模型请求越权或上下文持续增长，就很难回答三个关键问题：**发生了什么、允许做什么、应该从哪里继续**。

BearAgent 从运行时边界而不是功能数量开始设计：

| Durable execution | Authority & isolation | Trace & replay | Local-first |
|---|---|---|---|
| Run、Activity、Event 和安全边界恢复 | Grant、Policy、Approval 与独立 runner | 不可变事实、可重建投影和可比较轨迹 | 单用户、单进程、SQLite、CLI-first |
| 不承诺 exactly-once；不确定副作用进入 `UNKNOWN` | 模型和 Tool 输出不能自行授予权限 | 失败、重试、成本和 Artifact 均可检查 | 没有指标证明前不引入分布式组件 |

项目刻意保持“小而完整”：先把持久执行、权限隔离和失败语义做对，再增加 Web UI、Skills、MCP、Memory 或 Multi-Agent。

## Architecture

![BearAgent layered runtime architecture](docs/assets/bearagent-architecture.svg)

图中的绿色 `NOW` 表示已有代码与测试支撑的基础；`P1`—`P5` 表示已接受路线图中的目标阶段，而不是当前可用能力。视觉分层参考了 [DeepTutor](https://github.com/HKUDS/DeepTutor) 的 README 架构图；模块、依赖方向和阶段划分以 BearAgent 的 [总体架构](docs/architecture/overview.md)与[路线图](docs/project/roadmap.md)为准。

两条边界贯穿整个设计：

- Runtime Core 只依赖 BearAgent 领域类型与 Port，不导入模型 SDK、FastAPI、MCP、Docker 或数据库 Adapter。
- 所有外部副作用都必须经过 Tool Executor 与 Policy；事件是事实，Run/Activity 表、Checkpoint 和索引只是投影或缓存。

## Project status

| Available now | Building in P1 | Deliberately later |
|---|---|---|
| Python 3.12 + uv 工程基线 | Run reducer 与执行预算 | P2：checkpoint、resume、retry、`UNKNOWN` |
| `help`、`version`、`doctor` CLI | EventStore contract + SQLite | P3：Policy、Approval、Sandbox、HTTP/SSE |
| 类型化 ID、Message、Error、Event envelope | 一个真实 Model Provider 与有界 Agent Loop | P4：Web UI、Skills、MCP、Memory |
| Fake Model / Tool / In-memory Store | Workspace 只读工具与 `outputs/**` 原子写入 | P5：OpenTelemetry、replay、eval |
| Ruff、Pyright、pytest、跨平台 CI | `run`、`inspect`、`events` CLI | P6+：Multi-Agent、browser、多 worker |
| 中文 Starlight 学习与开发文档 | 可追踪的首个本地文件任务 | 仅在真实需求证明后扩展 |

当前权威状态见 [Project Roadmap](docs/project/roadmap.md) 和[公开文档状态页](site/src/content/docs/zh-cn/project/status.md)。Roadmap 中出现模块名称不等于它已经实现。

## Quick start

前置依赖：[uv](https://docs.astral.sh/uv/)。

```powershell
git clone https://github.com/CherryYang05/BearAgent.git
cd BearAgent
uv python install 3.12
uv sync --all-groups --locked
uv run bearagent --help
uv run bearagent doctor
```

机器可读诊断：

```powershell
uv run bearagent doctor --json
```

也可以通过 Python module 启动：

```powershell
uv run python -m bearagent doctor --json
```

## Development

运行完整 Python 与工程文档验证：

```powershell
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv run python scripts/check_docs.py
```

本地启动中文文档站：

```powershell
npm --prefix=site ci
npm run dev --prefix=site
```

然后访问 `http://localhost:4321/zh-cn/`。生产构建使用 `npm run build --prefix=site`。

## Repository layout

```text
BearAgent/
├── src/bearagent/
│   ├── domain/       immutable facts and value types
│   ├── runtime/      state transitions and execution kernel
│   ├── application/  commands and use cases
│   ├── ports/        model, tool and store contracts
│   ├── adapters/     provider, persistence, sandbox and test adapters
│   └── interfaces/   CLI now; HTTP API later
├── tests/
│   ├── architecture/ dependency-boundary checks
│   ├── contract/     schema compatibility
│   ├── security/     safe error behavior
│   ├── integration/  executable entry points
│   └── unit/         deterministic domain behavior
├── docs/             engineering source of truth
└── site/             public learning and developer documentation
```

## Roadmap

| Phase | Outcome | Status |
|---|---|---|
| P0 | Architecture, engineering baseline and documentation governance | Complete |
| P1 | Local CLI Agent with one Provider and bounded workspace tools | In progress |
| P2 | Durable recovery, cancel, retry, idempotency and `UNKNOWN` | Planned |
| P3 | Policy, approval, isolated runner and secure self-hosted beta | Planned |
| P4 | Web UI, Skills, MCP and inspectable Memory | Planned |
| P5 | Trace, replay, eval and public project evidence | Planned |

**P3 是第一个完整项目完成线。** 详细 Feature Backlog、验收标准和明确不做的内容都记录在[路线图](docs/project/roadmap.md)中。

## Documentation

- [文档索引](docs/index.md)：工程文档的推荐阅读顺序与权威层级。
- [总体架构](docs/architecture/overview.md)：领域模型、状态机、持久化、权限和安全边界。
- [AI 辅助开发 SOP](docs/development/ai-development-sop.md)：从调查到关闭 Feature 的完整流程。
- [Feature Specs](docs/specs/README.md)：可观察行为、失败语义和验收标准。
- [Implementation Plans](docs/plans/README.md)：当前 Feature 的可验证纵向切片。
- [Architecture Decision Records](docs/adr/README.md)：跨模块设计决策及其权衡。
- [本地文档站指南](site/README.md)：Starlight 的预览、构建与内容边界。

`docs/` 是工程 Source of Truth；`site/` 是由 Spec、ADR、代码和测试派生的公共学习与开发视图。每个 Feature 关闭时必须同步两者，并明确区分通用原理、已接受设计、当前实现和未来计划。

## Contributing

项目目前处于早期阶段，适合从小而边界清晰的改动开始。提交代码前：

1. 阅读 [`AGENTS.md`](AGENTS.md)、[总体架构](docs/architecture/overview.md)和[路线图](docs/project/roadmap.md)。
2. 找到对应 Feature Spec、Implementation Plan 与相关 ADR；聊天记录不作为实现依据。
3. 保持 diff 狭窄，为失败、安全和恢复语义补充相应测试。
4. 完成 Docs Impact 检查，并运行本 README 中的完整验证命令。

## License

许可证尚未决定。公开发布代码前会在 Apache-2.0 与 AGPL-3.0 之间通过 ADR 确认；在此之前，请不要假设拥有复制、修改或分发授权。
