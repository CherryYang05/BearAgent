<div align="center">

<h1>BearAgent</h1>
<p><strong>让个人 Agent 在本地可靠地完成长任务</strong></p>
<p><sub>过程能查看 · 结果不明时不猜 · 危险操作必须获准</sub></p>
<p>
  <a href="#当前状态"><img alt="P1 in progress" src="https://img.shields.io/badge/status-P1%20in%20progress-2563EB"></a>
  <a href="https://www.python.org/"><img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3776AB?logo=python&amp;logoColor=white"></a>
  <a href="https://docs.astral.sh/uv/"><img alt="uv package manager" src="https://img.shields.io/badge/package%20manager-uv-DE5FE9"></a>
  <a href="https://github.com/CherryYang05/BearAgent/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/CherryYang05/BearAgent/actions/workflows/ci.yml/badge.svg"></a>
</p>
</div>

> [!IMPORTANT]
> BearAgent 当前还不能执行真实 Agent 任务。仓库已经实现内部数据类型、Run/Activity 状态、Event
> Reducer、预算检查、SQLite EventStore、首个 OpenAI Responses adapter、统一 Tool 执行边界、受限
> workspace 读写工具、原子输出 Artifact 和本地文档站；ContextBuilder、完整 Agent Loop 与 Run CLI
> 仍在 P1 计划中。

## 从一个文件任务说起

假设用户提出：

> 阅读 `docs/` 中的架构和路线图，写一份项目介绍到 `outputs/intro.md`。

模型可以决定下一步读哪个文件，但它不应该自行决定能否读取任意路径、能否写到仓库其他位置，
也不能在工具超时后猜测文件是否已经写好。BearAgent 在模型之外提供一个 Runtime，负责：

1. 保存模型调用、工具操作、预算、错误和产物，使执行过程能够还原；
2. 只有在结果能够确认时才继续，无法确认的外部写入停下来处理；
3. 根据明确规则检查权限，模型和工具输出都不能给自己增加权限。

第一个可用场景是仓库与本地文档研究。P1 只读取指定工作区，并且只向 `outputs/**` 写入。
BearAgent 不以复刻 Manus、Claude Code 或堆叠模型、工具和 Agent 角色为目标。

## 架构一览

![BearAgent layered runtime architecture](docs/assets/bearagent-architecture.svg)

核心 Runtime 只使用 BearAgent 自己的 ID、Message、Event 和接口。具体模型 SDK、SQLite、CLI 和
未来的 HTTP API 都在外层 adapter 中。所有会改变外部世界的操作都经过统一的工具执行和权限入口。

详细说明见[总体架构](docs/architecture/overview.md)。图中的阶段标签表示路线图目标，不表示对应
模块已经实现。

## 当前状态

| 已有代码 | P1 还要接通 | 更晚再做 |
|---|---|---|
| Python 3.12 + uv 工程与 CI | ContextBuilder 和版本化 Agent 配置 | P2：崩溃恢复、Attempt、`UNKNOWN` |
| `help`、`version`、`doctor` | `run`、`inspect`、`events` | P3：Approval、隔离执行、安全自托管 |
| 类型化 ID、Message、Error、Event、Artifact | ContextBuilder 和有界 Agent Loop | P4：Skill、MCP、Web、Memory |
| Run/Activity 状态与五类预算 | ContextBuilder 与有界 Agent Loop | P5：持续追踪与跨版本评测 |
| SQLite EventStore、projection 与 migration | Tool Activity Event 接线 | P6+：多个 Agent、浏览器、分布式执行 |
| ModelProvider port 与 OpenAI Responses adapter | 固定任务集与可复现结果 | 只有真实需求出现后再扩展 |
| Tool Registry、固定 Policy、统一 Executor | Tool Activity Event 接线 | 只有真实需求出现后再扩展 |
| `workspace.list/read/search/write` 与路径边界 | 文件 Tool 与 Agent Loop 接线 | 只有真实需求出现后再扩展 |
| 中文 Starlight 文档站 | 端到端固定任务集 | 只有真实需求出现后再扩展 |

当前事实见[路线图](docs/project/roadmap.md)和[公开状态页](site/src/content/docs/zh-cn/project/status.md)。

## 快速开始

需要先安装 [uv](https://docs.astral.sh/uv/)：

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
uv run python -m bearagent doctor --json
```

## 开发和验证

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

访问 `http://localhost:4321/zh-cn/`。生产构建使用 `npm run build --prefix=site`。

## 代码从哪里读

```text
src/bearagent/
├── domain/       BearAgent 自己的 ID、消息、事件、状态和错误
├── runtime/      Reducer、预算和后续执行规则
├── application/  启动或查询 Run 的用例
├── ports/        Runtime 需要模型、工具、存储提供的行为
├── adapters/     Provider、SQLite、文件和测试实现
└── interfaces/   CLI；HTTP API 后置
```

测试按要验证的边界放在 `tests/unit/`、`contract/`、`integration/`、`recovery/`、`security/`。

## 阶段顺序

| 阶段 | 用户得到什么 | 状态 |
|---|---|---|
| P0 工程基础 | 仓库可安装、测试，开发规则明确 | 已完成 |
| P1 可检查执行 | 本地文件任务可完成，过程和失败可查看 | 进行中 |
| P2 失败恢复 | 中断后只从能确认的位置继续 | 未开始 |
| P3 权限与隔离 | 危险操作获准后执行，代码与宿主隔离 | 未开始 |
| P4 日常使用 | Skill、MCP、Web、Memory 依次接入 | 未开始 |
| P5 持续评测 | 比较质量、成本、恢复和安全回归 | 未开始 |

P3 是第一个可信 Runtime 完成线，不是成熟通用 Agent 产品的完成线。完整验收条件见
[项目路线图](docs/project/roadmap.md)。

## 文档入口

- [产品定位](docs/project/product-positioning.md)：为谁解决什么问题，为什么范围保持很小；
- [总体架构](docs/architecture/overview.md)：模块怎样连接，哪些边界长期成立；
- [Feature Specs](docs/specs/README.md)：每个功能必须做到什么；
- [Implementation Plans](docs/plans/README.md)：按什么顺序实现和验证；
- [ADRs](docs/adr/README.md)：为什么选择当前技术方案；
- [AI 辅助开发流程](docs/development/ai-development-sop.md)：怎样调查、定义、实现和关闭 Feature；
- [本地文档站](site/README.md)：面向学习和代码阅读的中文站点。

`docs/`、代码和测试保存工程事实；`site/` 用更连贯的例子解释这些事实。路线图和参考项目的能力
不能被写成当前实现。

## 参与开发

先阅读 [`AGENTS.md`](AGENTS.md)，再确认当前 Feature 的 Spec、ADR 和 Plan。修改保持范围清楚，
并用与风险相称的单元、契约、集成、恢复和安全测试证明行为。Feature 完成时同步工程文档、学习
说明、开发者入口和当前状态。

## License

许可证尚未决定。公开发布代码前会在 Apache-2.0 与 AGPL-3.0 之间通过 ADR 确认；在此之前，
不要假设拥有复制、修改或分发授权。
