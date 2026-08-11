<div align="center">

<h1>BearAgent</h1>
<p><strong>面向本地长任务、失败语义诚实的 Agent Runtime</strong></p>
<p><sub>A failure-honest Agent Runtime for inspectable, governed local task execution.</sub></p>
<p>
  <a href="#project-status"><img alt="P1 in progress" src="https://img.shields.io/badge/status-P1%20in%20progress-2563EB"></a>
  <a href="https://www.python.org/"><img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3776AB?logo=python&amp;logoColor=white"></a>
  <a href="https://docs.astral.sh/uv/"><img alt="uv package manager" src="https://img.shields.io/badge/package%20manager-uv-DE5FE9"></a>
  <a href="https://github.com/CherryYang05/BearAgent/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/CherryYang05/BearAgent/actions/workflows/ci.yml/badge.svg"></a>
</p>
<p>
  <a href="#why-bearagent">为什么是 BearAgent</a> ·
  <a href="docs/project/product-positioning.md">产品定位</a> ·
  <a href="#architecture">架构</a> ·
  <a href="#project-status">当前状态</a> ·
  <a href="#quick-start">快速开始</a> ·
  <a href="#roadmap">路线图</a> ·
  <a href="#contributing">参与开发</a>
</p>

</div>

> [!IMPORTANT]
> BearAgent 已完成 **P0 Engineering Baseline**，当前处于 **P1 Inspectable Execution**。领域契约与本地文档站已经实现；真实 Model Provider、Agent Loop、文件工具和 SQLite Run 尚不可用，因此它现在还不能执行真实 Agent 任务。

## Why BearAgent

很多 Agent demo 在 happy path 上只是 `model → tool → model` 循环。一旦进程中断、外部写入结果不确定、模型请求越权或上下文持续增长，就很难回答三个关键问题：**发生了什么、允许做什么、应该从哪里继续**。

成熟 Agent 已经普遍具备工具轨迹、会话恢复、审批或 sandbox 的一部分，BearAgent 不把“有这些功能”当作独占卖点。它聚焦的是更严格的一致执行契约，尤其在崩溃跨过外部副作用边界时，不用猜测掩盖未知结果：

| Durable facts | Failure-honest recovery | Model-independent authorization | Reference application |
|---|---|---|---|
| Run、Activity、Attempt、Event、预算和 Artifact 可检查 | 用 idempotency key、receipt、reconcile 与 `UNKNOWN` 表达真实结果 | Policy、Approval 和 runner 在模型之外强制执行 | 先用 Repo/Document Research Agent 验证真实本地长任务 |
| P1 打通可用的纵向任务闭环 | P2 在 kill-point 证明何时继续、重试或停住 | P3 证明参数篡改与权限绕过会被阻断 | P4 再验证受控 Skill/MCP 与日常体验 |

BearAgent 的结构是“可信执行内核 + 第一个参考应用”，而不是另一个只展示 Agent Loop 的框架，也不是 Claude Code/Manus 的功能复刻。完整的目标用户、竞品边界与表达规范见[产品定位](docs/project/product-positioning.md)。

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
| P1 | Reference execution：Repo/Document Research Agent 完成有界、受限、事实可查的本地任务 | In progress |
| P2 | Failure-honest recovery：checkpoint、resume、cancel、幂等、receipt、reconcile 与 `UNKNOWN` | Planned |
| P3 | Governed self-hosting：模型外授权、精确 Approval、隔离 runner 与安全自托管 | Planned |
| P4 | Daily-use experience：受控 Skill/MCP、Web UI 与可检查 Memory | Planned |
| P5 | Trace, replay, eval and public project evidence | Planned |

**P3 是第一个可信 Runtime 完成线，不等于成熟的通用 Agent 产品。** 详细 Feature Backlog、验收标准和明确不做的内容都记录在[路线图](docs/project/roadmap.md)中。

## Documentation

- [文档索引](docs/index.md)：工程文档的推荐阅读顺序与权威层级。
- [产品定位](docs/project/product-positioning.md)：目标用户、竞争边界、差异化证据与对外措辞。
- [总体架构](docs/architecture/overview.md)：领域模型、状态机、持久化、权限和安全边界。
- [AI 辅助开发 SOP](docs/development/ai-development-sop.md)：从调查到关闭 Feature 的完整流程。
- [Feature Specs](docs/specs/README.md)：可观察行为、失败语义和验收标准。
- [Implementation Plans](docs/plans/README.md)：当前 Feature 的可验证纵向切片。
- [Architecture Decision Records](docs/adr/README.md)：跨模块设计决策及其权衡。
- [本地文档站指南](site/README.md)：Starlight 的预览、构建与内容边界。

`docs/` 是工程 Source of Truth；`site/` 是由 Spec、ADR、代码和测试派生的公共学习与开发视图。每个 Feature 关闭时必须同步两者，并明确区分通用原理、已接受设计、当前实现和未来计划。

## Contributing

项目目前处于早期阶段，适合从小而边界清晰的改动开始。提交代码前：

1. 阅读 [`AGENTS.md`](AGENTS.md)、[产品定位](docs/project/product-positioning.md)、[总体架构](docs/architecture/overview.md)和[路线图](docs/project/roadmap.md)。
2. 找到对应 Feature Spec、Implementation Plan 与相关 ADR；聊天记录不作为实现依据。
3. 保持 diff 狭窄，为失败、安全和恢复语义补充相应测试。
4. 完成 Docs Impact 检查，并运行本 README 中的完整验证命令。

## License

许可证尚未决定。公开发布代码前会在 Apache-2.0 与 AGPL-3.0 之间通过 ADR 确认；在此之前，请不要假设拥有复制、修改或分发授权。
