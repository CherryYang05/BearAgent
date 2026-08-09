---
title: "Feature: P0 Engineering Baseline"
status: implemented
spec_id: F-0000
milestone: P0
owner: CherryYang05
created: 2026-08-09
last_updated: 2026-08-09
implemented_in: initial repository commit
related_adrs:
  - ADR-0006
---

# Feature: P0 Engineering Baseline

## 1. Background / Problem

BearAgent 已有架构、路线图和开发 SOP，但缺少可安装的 Python 包、稳定命令、测试基线、CI 和 Git 历史。继续开发 P1 会让 AI 在没有自动约束的情况下自行创造结构。

## 2. Goals

- G-1：建立 Python 3.12 + uv 的可复现工程和 lockfile。
- G-2：建立与架构一致的 domain/runtime/application/ports/adapters/interfaces 边界。
- G-3：提供 `bearagent --help`、`bearagent --version` 和 `bearagent doctor [--json]`。
- G-4：提供 FakeModelProvider、FakeTool 和 InMemoryEventStore 作为后续测试基础。
- G-5：在本地和 CI 运行 lint、type check、tests、import boundary 和文档链接检查。
- G-6：更新 README，使干净环境可以完成安装和验证。

## 3. Non-goals

- NG-1：不实现真实模型调用、Agent Loop 或 SQLite。
- NG-2：不实现文件工具、Policy、Approval、Sandbox、HTTP API 或 Web UI。
- NG-3：不引入 Pydantic/FastAPI/aiosqlite/httpx；它们在对应 Feature 使用时再加入。
- NG-4：不决定 P1 使用 Responses 还是 Chat Completions。

## 4. Terms and assumptions

- Fake 是测试 adapter，不进入生产 bootstrap。
- InMemoryEventStore 只保证单进程测试语义，不代表最终 SQLite schema。
- Python patch version 由 uv 在 `3.12` 系列内解析，仓库拒绝 3.13+。

## 5. User scenarios

### Scenario A：新环境启动

Given 一台安装了 uv 的机器，When 开发者执行 README 中的同步和验证命令，Then 项目安装成功且所有检查通过。

### Scenario B：环境诊断

Given BearAgent 已安装，When 执行 `bearagent doctor --json`，Then 返回机器可读的版本、Python、平台和工作目录信息，且不写入用户文件。

### Scenario C：AI 修改边界

Given runtime/domain/ports 的依赖约束，When 核心模块引入 FastAPI、MCP、Docker、provider SDK 或 adapter，Then architecture test 失败。

## 6. Functional requirements

- FR-1：包使用 `src/bearagent` layout，并能通过 console script 和 `python -m bearagent` 启动。
- FR-2：`doctor` 同时支持人类文本和 JSON，字段结构有测试。
- FR-3：Fake model/tool 记录收到的请求并返回预设结果。
- FR-4：InMemoryEventStore 按 Run 保存 Event，拒绝同一 Run 的非连续 sequence。
- FR-5：CI 在 Windows 和 Ubuntu 的 Python 3.12 上运行核心检查。
- FR-6：文档检查拒绝不存在的本地 Markdown 链接。

## 7. Interfaces

```text
bearagent --help
bearagent --version
bearagent doctor
bearagent doctor --json
python -m bearagent doctor --json
```

P0 的 Python ports 是内部测试契约，不承诺向后兼容；进入 P1 后由对应 Feature Spec 冻结。

## 8. State and data model

P0 不持久化生产状态。测试 Event 只包含 `event_id/run_id/sequence/event_type/payload`。最终 Event envelope 由 F-0001/F-0003 定义。

## 9. Failure and recovery semantics

- Python 版本不在 3.12 系列时，`doctor` 返回失败项并以非零码退出。
- InMemoryEventStore sequence 冲突抛出明确异常，不静默覆盖。
- 文档链接检查汇总全部错误后非零退出。
- P0 不涉及副作用恢复或 `UNKNOWN` Activity。

## 10. Security and privacy

- `doctor` 不读取或打印环境变量值、Git credential、API key 或主机敏感文件。
- Fake adapter 不进行网络或 shell 调用。
- CI 不需要任何 secret。

## 11. Observability

P0 只输出 CLI 诊断；结构化运行日志在 P1 定义。

## 12. Rollout and rollback

全部是新工程文件，无状态迁移。回滚为恢复提交前文件；lockfile 与 pyproject 必须同批变更。

## 13. Acceptance criteria

- AC-1：`uv sync --all-groups` 成功并生成 `uv.lock`。
- AC-2：`uv run bearagent --help`、`uv run bearagent doctor` 和 JSON 形式均成功。
- AC-3：Ruff、Pyright、pytest 和文档检查全部通过。
- AC-4：tests 覆盖 CLI、Fake adapters、InMemoryEventStore sequence 和 import boundary。
- AC-5：GitHub Actions 定义 Windows/Ubuntu Python 3.12 验证。
- AC-6：README 包含定位、范围、开发安装、验证、目录、路线图和文档入口。

## 14. Test plan

- Unit：doctor payload、Fake adapters、InMemoryEventStore。
- Contract：P0 只验证 fake 对 port 的结构一致性。
- Integration：console script 与 `python -m`。
- Recovery：None。
- Security：doctor 输出不包含环境值；import boundary。
- Manual：在 uv 管理的 Python 3.12 环境执行完整命令。

## 15. Documentation impact

- [x] Architecture
- [x] ADR
- [x] User docs
- [ ] Deployment docs
- [ ] Generated reference

## 16. Open questions

None。P1 模型协议和最终许可证继续保留为架构开放问题。
