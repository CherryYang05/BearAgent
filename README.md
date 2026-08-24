<div align="center">
  <img src="docs/assets/bearagent-logo.png" alt="BearAgent logo" width="176">
  <h1>BearAgent</h1>
  <p><strong>让个人 Agent 在本地可靠地完成长任务。</strong></p>
  <p>每一步可查看 · 结果不明时不乱重试 · 危险操作不由模型授权</p>
  <p>
    <a href="#项目状态"><img alt="P1 complete" src="https://img.shields.io/badge/status-P1%20complete-16A34A"></a>
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

> [!IMPORTANT]
> P1 已完成可检查执行。进程重启后自动恢复、Attempt、`UNKNOWN`、用户 Approval 和隔离 runner
> 仍未实现；这些分别属于 P2 和 P3。

## 现在可以做什么

- 从 CLI 启动一次本地文件 Run，并用 `inspect/events` 查看同一批已保存事实；
- 使用 SQLite 保存 Event 和 projection，查看每次模型/Tool Activity、预算、Error 与 Artifact；
- 显式选择 Responses、Chat Completions 或 Anthropic Messages 协议，不根据厂商或 URL 猜测；
- 通过默认拒绝 Policy 和 workspace 边界阻止路径逃逸、外部写入与 host code execution；
- 使用 model/tool/token/cost/time hard budget，让 Agent Loop 在明确上限内结束。

```powershell
uv run bearagent run "阅读 docs，并把项目简介写到 outputs/intro.md" `
  --config data/config.json `
  --profile data/p1-run-profile.json

uv run bearagent run inspect <run-id> --json
uv run bearagent run events <run-id> --after-sequence 0 --limit 100 --json
```

P1 的 Fake Provider 任务与真实模型 gate 都通过 5/5。真实 gate 的脱敏证据位于
[F-0017 P1 live report](docs/evidence/F-0017-p1-live-report-v1.json)。

## 快速开始

需要 [Git](https://git-scm.com/)、[uv](https://docs.astral.sh/uv/) 和 Python 3.12：

```powershell
git clone https://github.com/CherryYang05/BearAgent.git
cd BearAgent
uv python install 3.12
uv sync --all-groups --locked
uv run bearagent doctor
```

复制配置模板：

```powershell
Copy-Item config.example.json data/config.json
Copy-Item examples/run-profile-v2.example.json data/p1-run-profile.json
```

然后编辑两份本机文件：

1. 在 `data/config.json` 中填写 Provider 的 protocol、base URL、API key、model 和默认 model；
2. 在 `data/p1-run-profile.json` 中选择 `provider_id`，并按任务设置预算和 Tool 名单；
3. 运行上面的 `bearagent run` 命令。

仓库示例故意把预算设为 0，因此未修改时只会生成一个安全、可查询的 `budget_exhausted` Run，不会
调用模型。字段说明和密钥边界见[配置参考](docs/reference/configuration.md)；完整 CLI 教程见
[运行与检查一次 Run](site/src/content/docs/zh-cn/learn/run-inspect-events.md)。

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

准备修改代码时先阅读 [`AGENTS.md`](AGENTS.md)，再确认当前 Feature 的 Spec、ADR 和 Plan。

## License

许可证尚未决定。公开发布代码前会在 Apache-2.0 与 AGPL-3.0 之间通过 ADR 确认；在此之前，不要
假设拥有复制、修改或分发授权。
