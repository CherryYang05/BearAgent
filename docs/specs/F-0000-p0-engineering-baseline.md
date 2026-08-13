---
title: "Feature: P0 Engineering Baseline"
status: implemented
spec_id: F-0000
milestone: P0
owner: CherryYang05
created: 2026-08-09
last_updated: 2026-08-13
implemented_in: initial repository commit
related_adrs:
  - ADR-0006
---

# F-0000：建立可安装、可测试的工程基础

## 1. 为什么现在要做

BearAgent 已经有架构和路线图，但没有可安装的 Python 包、稳定 CLI、测试、CI 和自动边界检查。
如果直接开始 P1，后续代码会在没有可执行约束的情况下自行形成结构。

## 2. 本次交付

- G-1：Python 3.12 + uv 的可复现环境和 lockfile；
- G-2：与架构一致的 domain、runtime、application、ports、adapters、interfaces 边界；
- G-3：`help`、`version`、`doctor [--json]` 命令；
- G-4：Fake model、Fake tool 和内存 Event store，供后续确定性测试使用；
- G-5：本地与 CI 的格式、lint、类型、测试、依赖边界和文档链接检查；
- G-6：一份可以从干净环境执行的 README。

## 3. 本次不做

真实模型、Agent Loop、SQLite、文件工具、Policy、Approval、sandbox、HTTP API 和 Web UI 都不在 P0。
Pydantic、FastAPI、aiosqlite、httpx 也要等到实际 Feature 使用时再引入。P0 不决定 P1 的模型协议。

## 4. 需要先说明的约定

Fake 只用于测试，不进入生产组装。内存 Event store 只保证单进程测试行为，不预设最终 SQLite
schema。Python patch version 由 uv 在 3.12 系列中选择，仓库拒绝 3.13+。

## 5. 使用场景

### 新环境安装

开发者在一台只安装了 uv 的机器上执行 README 命令，项目能够安装，并通过全部基础检查。

### 环境诊断

`bearagent doctor --json` 返回机器可读的 BearAgent、Python、平台和工作目录信息，不写用户文件，
也不读取或打印环境变量值。

### 核心依赖边界

如果 domain、runtime 或 ports 导入 FastAPI、MCP、Docker、Provider SDK 或 adapter，architecture
test 必须失败。

## 6. 必须满足的行为

- FR-1：使用 `src/bearagent` layout，console script 和 `python -m bearagent` 都能启动；
- FR-2：`doctor` 同时提供人类文本和稳定 JSON 字段；
- FR-3：Fake model/tool 记录请求并返回预设结果；
- FR-4：内存 Event store 按 Run 保存 Event，拒绝非连续 sequence；
- FR-5：Windows 和 Ubuntu 的 Python 3.12 CI 都运行核心检查；
- FR-6：文档检查汇总并拒绝不存在的本地 Markdown 链接。

## 7. 对外入口和模块连接

```text
bearagent --help
bearagent --version
bearagent doctor
bearagent doctor --json
python -m bearagent doctor --json
```

P0 的 Python port 是后续测试底座，不承诺第三方兼容；P1 由对应 Spec 冻结具体数据和行为。

## 8. 状态和保存的数据

P0 不保存生产数据。测试 Event 只有最小 ID、Run、sequence、类型和 payload；F-0001/F-0003 后续
定义完整 Event 和数据库。

## 9. 失败时会发生什么

Python 不是 3.12 时，`doctor` 返回失败项并以非零码结束。sequence 冲突抛出明确异常，不覆盖旧
Event。文档检查报告全部坏链后失败。P0 没有恢复或 `UNKNOWN` 行为。

## 10. 安全与隐私

`doctor` 不打印环境变量、Git credential、API key 或敏感文件。Fake adapter 不访问网络或 shell，
CI 不需要 secret。

## 11. 怎样检查执行过程

P0 只有 CLI 诊断输出；结构化 Run 日志由 P1 定义。

## 12. 上线与回退

全部是新工程文件，没有数据迁移。回退代码时 `pyproject.toml` 和 `uv.lock` 必须一起恢复。

## 13. 验收标准

- AC-1：`uv sync --all-groups` 成功并生成 lockfile；
- AC-2：CLI help、doctor 和 JSON 形式均成功；
- AC-3：Ruff、Pyright、pytest 和文档检查通过；
- AC-4：测试覆盖 CLI、Fake adapter、内存 store sequence 和 import boundary；
- AC-5：GitHub Actions 覆盖 Windows/Ubuntu Python 3.12；
- AC-6：README 包含定位、当前范围、安装、验证、代码入口、路线图和文档入口。

## 14. 验证方式

- Unit：doctor payload、Fake adapter、内存 Event store；
- Contract：Fake 对 P0 port 的行为；
- Integration：console script 与 `python -m`；
- Security：doctor 不暴露环境值，核心 import boundary 生效；
- Recovery/Eval：不适用。

## 15. 文档同步

- [x] Architecture
- [x] ADR
- [x] README
- [ ] Deployment
- [ ] Generated reference

## 16. 尚未决定的问题

无。模型协议和许可证留给后续 Feature。
