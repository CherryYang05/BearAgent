<div align="center">
  <img src="docs/assets/bearagent-logo.png" alt="BearAgent logo" width="176">
  <h1>BearAgent</h1>
  <p><strong>让个人 Agent 在本地可靠地完成长任务。</strong></p>
  <p>每一步可查看 · 结果不明时不乱重试 · 危险操作不由模型授权</p>
  <p>
    <a href="#当前已经实现"><img alt="Local CLI ready" src="https://img.shields.io/badge/status-local%20CLI%20ready-16A34A"></a>
    <a href="https://www.python.org/"><img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3776AB?logo=python&amp;logoColor=white"></a>
    <a href="https://docs.astral.sh/uv/"><img alt="uv" src="https://img.shields.io/badge/package%20manager-uv-DE5FE9"></a>
    <a href="https://github.com/CherryYang05/BearAgent/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/CherryYang05/BearAgent/actions/workflows/ci.yml/badge.svg"></a>
  </p>
  <p>
    <a href="#快速开始">快速开始</a> ·
    <a href="docs/index.md">工程文档</a> ·
    <a href="docs/project/roadmap.md">Roadmap</a> ·
    <a href="site/src/content/docs/zh-cn/project/status.md">当前状态</a>
  </p>
</div>

BearAgent 是一个 local-first 的个人 Agent Runtime。它把模型调用、Tool、预算、Error 和 Artifact
保存成可查询事实，并把文件访问和外部副作用放在模型之外控制。

当前第一个可用场景是仓库与本地文档研究：Agent 可以在指定 workspace 中查找、读取和比较资料，
并且只向 `outputs/**` 写入结果。

## 快速开始

需要 [Git](https://git-scm.com/)、[uv](https://docs.astral.sh/uv/) 和 Python 3.12：

```console
git clone https://github.com/CherryYang05/BearAgent.git
cd BearAgent
uv python install 3.12
uv sync --all-groups --locked
uv run bearagent doctor
```

### 1. 准备本地配置

第一次运行前准备两个本机文件：

- 将根目录的 `config.example.json` 复制为 `data/config.json`；
- 将 `examples/run-profile-v2.example.json` 复制为 `data/p1-run-profile.json`。

在 `data/config.json` 中填写模型服务的 protocol、base URL、API key、model 和默认 model。在
`data/p1-run-profile.json` 中选择同一个 `provider_id`，并设置 Agent 指令、可用 Tool 和预算。

> [!IMPORTANT]
> 示例 RunProfile 的预算全部是 0。要真正调用大模型，必须先把模型次数、token、时间和 Tool 次数
> 等预算改为你愿意承担的非零上限。

这两个默认文件都位于 Git 忽略的 `data/` 目录。API key 只应保存在本机的 `data/config.json` 中。
字段说明见[配置参考](docs/reference/configuration.md)。

### 2. 从命令行调用模型

```console
uv run bearagent run "阅读 docs，并把项目简介写到 outputs/intro.md"
```

BearAgent 会自动读取 `data/config.json` 和 `data/p1-run-profile.json`，使用当前目录作为 workspace，
并把 Event 保存到 `data/bearagent.db`。只有需要临时使用其他文件时，才需要传 `--config`、`--profile`、
`--workspace` 或 `--database`。

命令结束后会输出 Run ID、最终状态、模型回答和生成的 Artifact。还可以查看保存下来的状态和 Event：

```console
uv run bearagent run inspect <run-id> --json
uv run bearagent run events <run-id> --after-sequence 0 --limit 100 --json
```

Run profile 只保存非敏感 `AgentConfig` 和预算；API key/base URL 只能来自进程环境。当前仓库只用
注入式 Fake Provider 自动验证这条链，真实模型配置和 P1 退出演练仍待完成。安装状态、profile 字段、
所有命令选项、退出码与排错方式统一维护在
[P1 命令行完整使用手册](site/src/content/docs/zh-cn/guides/cli.md)。

## 当前已经实现

- 从 CLI 启动一次真实模型文件任务，并用 `inspect/events` 查看同一批已保存事实；
- 使用 SQLite 保存 Event 和 projection，查看每次模型/Tool Activity、预算、Error 与 Artifact；
- 显式选择 Responses、Chat Completions 或 Anthropic Messages 协议，不根据厂商或 URL 猜测；
- 在 workspace 内列出、读取和搜索文件，并且只向 `outputs/**` 原子写入完整结果；
- 通过默认拒绝 Policy 和 workspace 边界阻止路径逃逸、外部写入与 host code execution；
- 使用 model/tool/token/cost/time hard budget，让 Agent Loop 在明确上限内结束。

固定离线任务与真实模型任务均通过 5/5。真实模型任务的脱敏证据位于
[live-model report](docs/evidence/F-0017-p1-live-report-v1.json)。

## 为什么是 Runtime

模型可以提出下一步，但不应该自己回答这些问题：

| 问题 | BearAgent 的阶段 |
|---|---|
| 发生了什么？ | P1 已完成：Event、Reducer、预算和查询 |
| 失败后怎样继续才安全？ | P2 下一步：Attempt、Receipt、reconcile、`UNKNOWN` |
| 动作是否获准，只能影响哪里？ | P3：参数绑定 Approval 和隔离 runner |

Routing、MCP、Web、Memory 和多个 Agent 不会抢在这条执行—恢复—授权主线之前。完整边界和 Feature
顺序见 [Roadmap](docs/project/roadmap.md)。

## 项目状态

| 阶段 | 状态 | 结果 |
|---|---|---|
| P0 工程基础 | 已完成 | 可安装、可测试，模块和文档规则明确 |
| P1 可检查执行 | 已完成 | 本地文件任务可完成，过程与失败可查询 |
| P2 可恢复执行语义 | 下一阶段 | 中断后根据证据复用、重试、核对或停下 |
| P3 授权与隔离执行 | 规划中 | 危险动作获准后只在受控 runner 中执行 |
| P4 接入与日常使用 | 更晚 | HTTP、自托管、Skill、MCP、Web、Memory |

## 文档

- [从哪里开始读](docs/index.md)
- [产品定位](docs/project/product-positioning.md)
- [总体架构](docs/architecture/overview.md)
- [Feature Specs](docs/specs/README.md)
- [ADRs](docs/adr/README.md)
- [本地中文学习站](site/README.md)

`docs/`、代码和测试保存工程事实；`site/` 用同一个文件任务解释这些事实。Roadmap 中的能力不等于
当前已经实现。

## 开发

```powershell
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv run python scripts/check_docs.py
npm.cmd run build --prefix=site
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
- [P1 命令行完整使用手册](site/src/content/docs/zh-cn/guides/cli.md)：安装、配置、运行、查询和排错；
- [本地文档站](site/README.md)：面向学习和代码阅读的中文站点。

`docs/`、代码和测试保存工程事实；`site/` 用更连贯的例子解释这些事实。路线图和参考项目的能力
不能被写成当前实现。

## 参与开发

先阅读 [`AGENTS.md`](AGENTS.md)，再确认当前 Feature 的 Spec、ADR 和 Plan。修改保持范围清楚，
并用与风险相称的单元、契约、集成、恢复和安全测试证明行为。Feature 完成时同步工程文档、学习
说明、开发者入口和当前状态。

## License

许可证尚未决定。公开发布代码前会在 Apache-2.0 与 AGPL-3.0 之间通过 ADR 确认；在此之前，不要
假设拥有复制、修改或分发授权。
