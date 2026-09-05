---
title: "Plan: safe local startup and P1 closure review"
status: active
plan_id: PLAN-F-0032
related_spec: F-0032
---

# PLAN-F-0032：修复默认访问边界，完成首次使用和 P1 收口审查

关联 [F-0032](../specs/F-0032-safe-local-startup.md) 与
[ADR-0018](../adr/ADR-0018-runtime-files-outside-workspace-tools.md)。

2026-09-05 基线为 `de99e78`；Windows 离线测试 490 passed。临时伪造 config 同时被 read/search 读取，
因此历史 P1 gate 不足以关闭本轮安全收口。Future 的可读取讨论用于研究方向；附件原文未由接口提供，
不把讨论摘要当作 RP 原文或既有算法效果证据。

## 切片

- [x] 统一保护默认运行资料、自定义配置与数据库，增加生产路径的泄漏回归。
- [x] 增加无覆盖初始化和离线配置检查，完整走通新手命令。
- [x] 重写首次运行路径，校准费用、事实与恢复声明；补齐架构审查和科研规划。
- [x] 跑完整质量门、构建、链接和浏览器阅读检查，记录当前环境限制。
- [x] 安装受限部署身份，并验证 forced command、原子发布、失败回退边界和公网健康检查。
- [x] 按项目所有者发布指令记录不可变实现提交，并推送功能分支。
- [ ] workflow 进入 `main` 后验证真实 push 触发，再更新 Spec 状态并关闭 Plan。

## 验证记录

2026-09-06，Windows / Python 3.12.13 最终结果如下。所有 Python 命令使用仓库专用 `UV_CACHE_DIR`。

| 检查 | 结果 |
|---|---|
| `uv run pytest`，使用本次审查的独立临时/缓存目录 | 507 passed，29.51 秒；包含 contract/schema、integration、security、recovery 和 evals |
| 两个新增回归文件 | 17 passed；真实硬链接别名、伪造凭据的生产路径与 Event/Context、离线初始化和默认 CLI 流程 |
| `uv lock --check` | 通过，锁文件未改动 |
| `uv run ruff format --check .` / `uv run ruff check .` | 273 个文件格式通过；lint 通过 |
| `uv run pyright` | 0 errors，0 warnings |
| `uv run python scripts/check_docs.py` | 152 个 Markdown 文件的本地链接通过 |
| `uv run python scripts/check_governance.py` | 15 Specs、14 Plans、19 ADRs 一致 |
| `npm run build --prefix=site` | 48 页、Pagefind 搜索索引与 sitemap 构建成功 |
| `uv build --offline` | sdist 与 wheel 成功；普通 build 因本机网络权限无法访问 PyPI，改用已有缓存 |
| 已安装 wheel 的 `scripts/smoke_wheel_cli.py` | 独立 `uv run --no-project --offline --with ...whl` 环境，Fake Run/inspect/events 通过 |
| 浏览器阅读 | 本地生产预览；浅色/深色、桌面与 390px 窄屏实看；修正标题断行及过小的横向 Mermaid |
| `git diff --check` | 通过 |

页面检查包括首次运行步骤、配置表格、研究流程图与导航。窄屏实测 document scrollWidth 等于 clientWidth；
Pagefind 搜索 init 返回 8 个结果，包含新增教程；首页两个运行入口均指向 first-run。
本地预览证据之外，站点随后按项目所有者授权部署到 `https://docs.bearguin.cn/zh-cn/`。Astro 已使用该
正式 URL 生成 sitemap；站点仍有原有的大 bundle 提示。
本轮没有重新执行付费模型 gate，也没有运行远端 Linux CI。现有真实 5/5 仅作为历史证据。

首次访问因站点虚拟主机尚未创建而返回 `ERR_SSL_UNRECOGNIZED_NAME_ALERT`。项目所有者在 1Panel 创建
`docs.bearguin.cn` 后，本轮停用空的 4321 反向代理，将 226 个静态文件发布到站点 index 目录；代理和
原目录备份在服务器 `/opt/1panel/backup/website/docs.bearguin.cn/20260905-1540/`。OpenResty 配置检查
与 reload 成功，公网 HTTPS、首页、新手/研究页面、Logo 和 Pagefind 均验证；390px 无横向溢出。

2026-09-06，服务器安装 root 管理的部署脚本与 forced-command 入口。专用 Ed25519 身份尝试 `id` 时以
64 拒绝；同一身份从标准输入接收构建包后成功发布 `20260905T163326Z-3869142`。仓库固定的服务器
host key 指纹已核对，`DOCS_DEPLOY_KEY` 已写入 GitHub Actions Secret，本机与服务器 `/tmp` 中转密钥
和压缩包均已删除。修正文档后的构建发布为 `20260905T163821Z-3870968`，公网状态页和 Pagefind 返回
最新内容；补齐正式站点 URL 后的 sitemap 构建发布为 `20260905T164020Z-3871728`。学习路线统一为
“第一步”到“第六步”后的最新版本为 `20260905T180426Z-3900412`。真实 main push 触发仍需等本分支
获准提交并进入 `main`，所以该切片保持未完成。

项目所有者随后在 1Panel 将 `docs.bearguin.cn` 明确切换为静态网站。1Panel 重新初始化 index 目录后曾
短暂只剩默认首页并使 `/zh-cn/` 返回 404；生效的 OpenResty `root` 已确认仍映射到发布脚本管理的
`/opt/1panel/www/sites/docs.bearguin.cn/index`。最新构建重新发布为
`20260905T184339Z-3914237`，公网首页、学习页、Pagefind 与 sitemap 均通过；配置不再包含 4321 反向代理。

初始化的 link/junction 拒绝测试用受控 junction 判定覆盖拒绝分支；真实文件链接的跨平台行为由既有
文件工具安全测试覆盖。这不宣称已完成恶意本机并发目录替换防护。

项目所有者已授权提交和推送。实现提交 `66064df` 已推送到
`origin/codex/F-0032-safe-local-startup`，远端 hash 与本地一致；该分支没有既有 PR，也没有分支 push
检查。部署 workflow 只监听 `main`，因此不能把功能分支推送或手工服务器发布写成 main trigger 证据。
Spec 保持 accepted、`implemented_in` 保持 null，本 Plan 保持唯一 active Plan，待合并后的第一次真实
workflow 成功再关闭。
