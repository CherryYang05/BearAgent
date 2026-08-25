---
title: 怎样把 BearAgent wheel 发布到 PyPI
description: 在公开发布门槛满足后构建 sdist/wheel、上传 PyPI，并从无源码环境验证安装结果。
bearStatus: mixed
sourceRefs:
  - F-0000
  - pyproject.toml
  - README
---

`uv build` 成功只说明仓库可以生成 distribution。用户能够执行 `pip install bearagent`，还需要维护者
选择一个版本，把同一批 sdist/wheel 上传到 PyPI，并从不含源码的环境重新验证。

```text
Git tag 对应的源码
        ↓ uv build --no-sources
sdist + wheel
        ↓ 检查内容和隔离安装
PyPI release
        ↓ pip install bearagent==<version>
用户环境中的 bearagent 命令
```

:::caution[当前只完成本地构建]
BearAgent 尚未在本分支声明 PyPI 发布完成。许可证仍待项目决策，PyPI 的 `bearagent` 名称归属也必须
在发布时重新确认。下面是 release runbook，不是现在立即执行 `uv publish` 的授权。
:::

## 发布前先过五道门

1. **许可证已经确定。** wheel 和 sdist 会公开分发代码；不能绕过仓库中尚未完成的许可证决策。
2. **项目名和账户已确认。** `pyproject.toml` 使用 `bearagent`，但 PyPI 名称全局唯一；发布账号必须
   确认项目归属，用户文档才能链接正式项目页。
3. **版本对应唯一源码。** 发布版本、Git tag、wheel 与 sdist 必须来自同一个已审查 commit。不要用
   相同版本号发布不同内容。
4. **完整检查已经通过。** Ruff、Pyright、pytest、文档链接、站点构建和安装包 smoke test 都要记录
   可复现结果。
5. **发布凭据不进仓库。** 优先使用 PyPI Trusted Publisher；手工发布时使用 project-scoped token，
   不把 token 写进命令示例、配置文件、日志或 Event。

## 从干净源码构建 distribution

先确认版本和工作树，再运行仓库的完整检查。发布构建使用：

```powershell
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv run python scripts/check_docs.py
npm run build --prefix=site
uv build --no-sources
```

`uv build --no-sources` 会在 `dist/` 生成两类文件：

```text
bearagent-<version>.tar.gz
bearagent-<version>-py3-none-any.whl
```

sdist 保存用于重新构建的源码与 metadata；wheel 是安装工具可以直接安装的 built distribution。
发布前要检查二者都来自本次构建，并确认 wheel 包含 CLI 模块和运行时资源。

## 先在无源码环境验证 wheel

不要只在仓库的开发环境里运行 `uv run bearagent`。开发环境可能直接读取 checkout，使漏打包文件不易
暴露。创建新的 Python 3.12 虚拟环境，安装具体 wheel，再执行：

```powershell
bearagent --version
bearagent doctor
python -m bearagent doctor --json
```

通过标准是：命令入口存在、版本与待发布版本一致、`doctor` 成功，并且测试进程不从源码 checkout
导入 `bearagent`。

## 上传到 PyPI

当所有门槛满足后，`uv publish` 默认把 `dist/` 中的 distribution 上传到 PyPI：

```powershell
uv publish
```

凭据通过发布环境注入。GitHub Actions 可以配置 PyPI Trusted Publisher，从而不保存长期 token；本地
手工发布则使用 `UV_PUBLISH_TOKEN` 或 `--token`，但不得把真实值提交或复制到公开日志。

PyPI 不允许用新内容覆盖已经发布的同版本文件。上传部分失败时，只能重试完全相同的 artifacts；如果
内容发生变化，先修复问题并增加版本号，再重新构建和发布。

官方命令和认证选项以
[uv 构建与发布指南](https://docs.astral.sh/uv/guides/package/)为准。第一次发布建议先走独立审核和
TestPyPI 演练，正式发布动作仍需要项目所有者明确授权。

## 发布后从索引重新验证

清空本地源码影响后，固定版本验证：

```powershell
python -m pip install "bearagent==<version>"
bearagent --version
bearagent doctor
```

也可以按 uv 官方建议使用临时环境：

```powershell
uv run --with "bearagent==<version>" --no-project -- bearagent doctor
```

最后在[从 PyPI 安装 BearAgent](/zh-cn/guides/install-from-pypi/)中把状态更新为 implemented，加入实际
PyPI 项目链接、首个可安装版本和该版本支持的 CLI 命令。发布 wheel 不代表路线图中尚未实现的功能
也已经可用。
