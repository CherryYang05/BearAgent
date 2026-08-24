<div align="center">

<h1>BearAgent</h1>
<p><strong>让个人 Agent 在本地可靠地完成长任务</strong></p>
<p><sub>过程能查看 · 结果不明时不猜 · 危险操作必须获准</sub></p>
<p>
  <a href="#当前状态"><img alt="P1 complete" src="https://img.shields.io/badge/status-P1%20complete-16A34A"></a>
  <a href="https://www.python.org/"><img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3776AB?logo=python&amp;logoColor=white"></a>
  <a href="https://docs.astral.sh/uv/"><img alt="uv package manager" src="https://img.shields.io/badge/package%20manager-uv-DE5FE9"></a>
  <a href="https://github.com/CherryYang05/BearAgent/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/CherryYang05/BearAgent/actions/workflows/ci.yml/badge.svg"></a>
</p>
</div>

> [!IMPORTANT]
> BearAgent 已接通本地 `run/inspect/events` CLI、SQLite、三种模型协议 adapter、受限 workspace
> Tools 和有界 Agent Loop。F-0017 的 DeepSeek V4 suite v1.1.1 真实 gate 已通过 5/5，P1 已关闭；
> P2 的崩溃恢复、Attempt 和 `UNKNOWN` 仍未开始。

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

| 已有代码 | P1 完成证据 | 更晚再做 |
|---|---|---|
| Python 3.12、uv、CI 与文档站 | 全量测试、链接、35 页站点、sdist/wheel 和隔离 smoke 通过 | P2：崩溃恢复、Attempt、`UNKNOWN` |
| `doctor`、`run`、`inspect`、`events` | 四个普通任务与一个安全 canary 真实 5/5 | P3：Approval、隔离执行、安全自托管 |
| 类型化领域数据、Reducer 与五类预算 | 最终 P1 Reality Check 通过 | P4：Skill、MCP、Web、Memory |
| SQLite EventStore 与 version 1 migration | 五个独立数据库重开后状态、Event 和 Artifact 一致 | P5：持续追踪与跨版本评测 |
| 三种模型协议 adapter、Agent Loop 和 production composition | Fake 5/5 与 DeepSeek V4 live 5/5 分开记录 | P6+：多个 Agent、浏览器、分布式执行 |
| Registry、固定 Policy 与受限 workspace Tools | 路径拒绝、预算终止和 canary 检查通过 | 只有真实需求出现后再扩展 |

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
uv run bearagent run --help
```

机器可读诊断：

```powershell
uv run bearagent doctor --json
uv run python -m bearagent doctor --json
```

F-0005 的命令入口已经实现：

```powershell
uv run bearagent run "整理 workspace 中的资料" --profile data/p1-run-profile.json --config data/config.json
uv run bearagent run inspect <run-id> --json
uv run bearagent run events <run-id> --after-sequence 0 --limit 100 --json
```

F-0017 把“服务怎样连接”和“本次 Run 用哪个服务”分开：

- 根目录的 [config 示例](config.example.json)保存厂商名、协议、base URL、
  直接填写的本机 key、模型列表和默认模型；
- [RunProfile v2 示例](examples/run-profile-v2.example.json)通过 `provider_id` 选服务，并保存
  Agent 指令、Tool 白名单和预算，不重复保存 model；
- [配置参考](docs/reference/configuration.md)记录字段类型、校验规则、选择行为和密钥边界；
- `data/config.json` 被 Git 忽略且拒绝 `pricing`；真实 key 只写在这份本机 config 中。objective 每次可以不同，不需要重新生成配置。

当前 production composition 支持 `openai_responses`、`openai_chat_completions` 和
`anthropic_messages` 三种 wire protocol。它不会根据厂商、URL 或 model 猜协议，也不会失败后
自动切换 endpoint。RunCreated v3 只保存可审计的 provider/model/protocol/pricing 选择，不保存 base URL、
key。详见[配置一次模型服务，运行不同目标](site/src/content/docs/zh-cn/learn/configure-model-service.md)
和[从命令行运行并检查一次 Run](site/src/content/docs/zh-cn/learn/run-inspect-events.md)。

v1/v2 安全模板都把预算设为 0。执行后会保存明确的 `budget_exhausted` Run，不创建 SDK client，也不
调用模型或 Tool。普通 Run 的内部价格版本是 `unpriced`。F-0017 的 live runner 也默认关闭；只有显式
确认 provider、model、独立 pricing snapshot、commit 和总费用上限后才允许产生真实请求。
2026-08-23 的 suite v1.1.1 使用 DeepSeek V4 经 production composition 通过 5/5；脱敏证据见
[F-0017 P1 live report v1](docs/evidence/F-0017-p1-live-report-v1.json)。


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
| P1 可检查执行 | 本地文件任务可完成，过程和失败可查看 | 已完成 |
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
