# BearAgent 工程文档：先找答案，再读记录

`docs/` 不是教程站的备份。它保存项目可审查的事实：范围、决定、验收条件、实施进度和配置契约。
如果你是第一次接触 Agent，请先从[中文学习书](../site/src/content/docs/zh-cn/index.mdx)开始；如果你准备
修改代码，再从本页进入。

## 第一次进入仓库，只读这四处

1. [总体架构](architecture/overview.md)：一次 Run 怎样穿过模块，哪些边界不能被绕过；
2. [项目路线图](project/roadmap.md)：当前阶段交付什么，未来能力明确不算当前实现；
3. [Feature 索引](specs/README.md)：当前 Feature 必须出现哪些可观察行为；
4. 当前 Feature 的 Spec、相关 [ADR](adr/README.md) 和唯一 active [Plan](plans/README.md)。

真正开始改代码前，再读 [AI 辅助开发流程](development/ai-development-sop.md)与根目录
[`AGENTS.md`](../AGENTS.md)。只想运行 P1 CLI 时，不必先读工程记录，直接使用
[命令行完整手册](../site/src/content/docs/zh-cn/guides/cli.md)。

## 一个疑问应该去哪找

| 你问的问题 | 事实来源 | 不要误用 |
|---|---|---|
| BearAgent 为谁解决什么问题 | [产品定位](project/product-positioning.md) | 不用 Roadmap 猜当前功能 |
| 当前阶段和关闭证据是什么 | [Roadmap](project/roadmap.md) | 阶段表不是实现细节 |
| 一个 Feature 必须做到什么 | Feature Spec + 验收测试 | Spec 不规定每一行代码 |
| 为什么选择这个跨模块方案 | ADR | `accepted` 不等于代码完成 |
| 当前按什么顺序实施 | 唯一 active Plan | Plan 勾选不能替代测试 |
| 模块现在怎样连接 | Architecture + 当前代码 | 历史图不能覆盖代码事实 |
| 一个行为是否真的成立 | 代码、测试、可复现命令 | 聊天记录和 README 都不是最终证据 |
| Spec/Plan/ADR 状态是否一致 | `scripts/check_governance.py` | 索引和站点不能建立第二份状态 |
| 用户怎样配置和操作 | CLI 手册 + [配置参考](reference/configuration.md) | 不让用户从 Spec 拼操作步骤 |

## 三种工程文档分别怎样读

### Feature Spec：读“结果必须长什么样”

先看“为什么做”和“本次不做”，再看必须满足的行为、失败表现和验收标准。Spec 中的 `status` 才是
Feature 状态；Feature ID 全局稳定，移动阶段也不改编号。

### ADR：读“为什么选这个方案”

先看要解决的问题和比较过的方案，再看决定、代价、回退和验证。ADR 的 `accepted` 只表示这项决定
生效，不表示关联 Feature 已实现。

### Implementation Plan：读“这次准备怎样落地”

Plan 保存切片顺序、接入点、测试和回退。全仓库最多一个主 Plan 为 `active`。如果 Plan 说已完成而
代码或测试不支持，先修正文档状态，不能按勾选框宣布功能成立。

## 状态词只表达一件事

| 状态 | 含义 |
|---|---|
| `draft` | 仍在讨论，不能据此实现 |
| `accepted` | 已同意范围或决定，可以作为实现依据 |
| `active` | 当前 Plan 正在实施，仍可能有未完成步骤 |
| `implemented` / `completed` | 验收和相应验证已经完成 |
| `superseded` | 已被新文档替代，保留用于理解历史 |

不要把“设计已接受”“本地代码已写完”“PR 已合并”“某个地址可访问”写成同一个状态。F-0015 的
验收对象是仓库中的文档内容、站点构建和阅读体验；是否把静态产物部署到某个平台不属于这个 Feature。

## 代码和文档怎样保持一致

每个 Feature 关闭时判断四个面：

1. `docs/` 中的 Spec、ADR、Plan 和架构事实；
2. `site/` 中初学者会读到的概念和使用路径；
3. `site/` 中开发者会跟随的源码与测试入口；
4. 当前状态页和阶段结果。

受到影响的表面写出更新路径；没有影响的表面写 `N/A` 和具体原因。不要求内部重构为了完成清单而
修改四种页面。S1 使用精简 Spec，只有多片实施时才增加 Plan；S2 才使用完整 Spec、ADR 和 active
Plan。

页面先写读者会遇到的具体问题，再引入 Runtime、port、adapter、Event、Reducer 等精确术语。不要为
了“更中文”另造一套同义词，也不要用搜索替换把旧状态机械改成新状态。改完后把段落连续读一遍，
并运行 `uv run python scripts/check_docs.py`、`uv run python scripts/check_governance.py`；站点受到影响
时再运行 `npm.cmd run build --prefix=site`。
