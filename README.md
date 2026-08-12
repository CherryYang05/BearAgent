<div align="center">

<h1>BearAgent</h1>
<p><strong>让个人 Agent 在本地可靠地完成长任务</strong></p>
<p><sub>Every step is inspectable. Uncertain actions are never guessed. Risky actions require permission.</sub></p>
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
> BearAgent 已完成 **P0 工程基础**，当前处于 **P1 可检查执行**。领域数据结构和本地文档站已经实现；真实模型、执行循环、文件工具和 SQLite 任务记录尚不可用，因此它现在还不能执行真实 Agent 任务。

## Why BearAgent

让模型调用工具并不难。真正把一个耗时较长的任务交给 Agent 后，困难通常出现在模型循环之外：进程可能中断，写文件可能已经发生却没有留下成功记录，模型也可能请求它本来不该使用的工具。

BearAgent 先把三个问题做清楚：

1. **它做过什么？** 每次模型调用、工具操作、错误和产物都可以查看。
2. **失败后怎么办？** 只有能确认结果时才继续；无法判断时停下来告诉用户，不把猜测当成功。
3. **它可以做什么？** 权限由运行时检查，模型看到的一段文字不能给自己增加权限。

项目首先用一个“仓库与本地文档研究助手”验证这些能力：它在限定目录中阅读资料、整理内容，并且只向 `outputs/**` 写入结果。BearAgent 不是 Claude Code 或 Manus 的复刻，也不追求在早期支持最多模型、工具和角色。完整说明见[产品定位](docs/project/product-positioning.md)。

## Architecture

![BearAgent layered runtime architecture](docs/assets/bearagent-architecture.svg)

图中的绿色 `NOW` 表示已有代码与测试支撑的基础；`P1`—`P5` 表示已接受路线图中的目标阶段，而不是当前可用能力。视觉分层参考了 [DeepTutor](https://github.com/HKUDS/DeepTutor) 的 README 架构图；模块、依赖方向和阶段划分以 BearAgent 的 [总体架构](docs/architecture/overview.md)与[路线图](docs/project/roadmap.md)为准。

两条规则贯穿整个设计：

- 核心执行代码不直接依赖模型厂商、Web 框架、MCP、Docker 或具体数据库，外部实现可以替换。
- 所有会改变外部世界的操作都经过同一个执行与权限入口，并留下可追溯记录。

## Project status

| 现在已有 | P1 正在建设 | 明确后置 |
|---|---|---|
| Python 3.12 + uv 工程基础 | 任务状态、限制和 SQLite 记录 | P2：中断后的恢复与不确定结果处理 |
| `help`、`version`、`doctor` 命令 | 一个真实模型和有界执行循环 | P3：审批、隔离执行和安全自托管 |
| 类型化 ID、消息、错误和事件外壳 | 受限的工作区读取与 `outputs/**` 写入 | P4：Web UI、Skills、MCP、Memory |
| 测试用模型、工具和内存存储 | `run`、`inspect`、`events` 命令 | P5：跨版本追踪、回放和评测平台 |
| Ruff、Pyright、pytest、跨平台 CI | 固定任务集与可复现评测记录 | P6+：多个 Agent、浏览器控制、分布式执行 |
| 中文 Starlight 学习与开发文档 | 可复现的仓库与文档任务集 | 仅在真实需求证明后扩展 |

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

| 阶段 | 做到什么 | 状态 |
|---|---|---|
| P0 工程基础 | 仓库可安装、可测试、边界和文档规则明确 | 已完成 |
| P1 可检查执行 | 真实本地任务可以完成，过程、限制和失败都能查看 | 进行中 |
| P2 失败恢复 | 进程中断后只从可确认的位置继续，不确定的操作不会被自动重做 | 规划中 |
| P3 权限与隔离 | 危险操作必须获准，代码在隔离环境运行，并可安全自托管 | 规划中 |
| P4 日常使用 | 依次接入 Skill、MCP、Web UI 和带来源的 Memory | 规划中 |
| P5 持续评测 | 比较任务质量、执行路径、成本、恢复和安全回归 | 规划中 |

**P3 是第一个可信运行时完成线，不等于成熟的通用 Agent 产品。** 每一阶段都必须用同一组真实任务和失败测试证明，不能仅凭架构图或功能清单关闭。详细范围见[路线图](docs/project/roadmap.md)。

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
