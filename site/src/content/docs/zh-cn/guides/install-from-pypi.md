---
title: PyPI 安装状态
description: 为什么当前仍建议从源码运行，以及正式发布后怎样验证安装包。
bearStatus: mixed
sourceRefs:
  - F-0000
  - pyproject.toml
---

你希望在一台没有 BearAgent 源码的机器上直接执行：

```powershell
python -m pip install bearagent
bearagent doctor
```

这条路径依赖两个不同事实：仓库已经能构建 wheel；维护者还必须把某个版本发布到 PyPI。当前仓库
已经验证前一个事实，尚未确认后一个事实。因此，正式发布前执行 `pip install bearagent` 可能得到
“找不到匹配版本”，不能把下面的发布后命令当成当前上线声明。

:::caution[当前尚未声明 PyPI 已发布]
`pyproject.toml` 中的项目名是 `bearagent`，但正式发布前还要确定许可证、确认 PyPI 名称归属并完成
一次发布演练。本站会在发布完成后把本页状态改为 implemented，并链接实际 PyPI 项目页。
:::

## 发布后怎样安装

BearAgent 当前要求 Python 3.12。建议使用独立虚拟环境，避免它的依赖影响其他项目。

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install bearagent
```

### macOS 或 Linux

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install bearagent
```

`pip` 会从 PyPI 选择与 Python 版本和平台兼容的 distribution。BearAgent 的纯 Python wheel 可以直接
安装；如果没有合适的 wheel，PyPI 同时发布的 sdist 允许安装工具按构建配置生成 wheel。

## 怎样确认命令来自安装包

安装完成后执行：

```powershell
bearagent --version
bearagent doctor
python -m bearagent doctor --json
```

`pyproject.toml` 把 `bearagent` 注册为 console script，所以激活虚拟环境后可以直接使用这个命令。
`doctor` 检查 Python、BearAgent 版本和当前运行环境，不读取模型密钥，也不执行 Agent 任务。

当前源码和本地构建 wheel 已包含 `doctor` 与 `run/inspect/events`，并通过隔离 wheel smoke；但这些
事实仍不能证明 PyPI 上已有对应版本。正式发布后，本页还要核对实际项目页、版本号、文件 hash 和
从空环境安装后的四组命令，再把状态改为 `implemented`。

## PyPI 发布前怎样测试本地 wheel

维护者还没有上传 PyPI 时，可以把 `dist/` 中的 wheel 复制到测试机器，再用具体文件名安装：

```powershell
python -m pip install .\dist\bearagent-<version>-py3-none-any.whl
bearagent doctor
```

这条命令验证“安装包能否使用”，但不验证 PyPI 项目、下载路径或发布权限。不要在文档中把一次本地
wheel 安装说成 PyPI 已经上线。

## 常见失败怎样判断

| 现象 | 先检查什么 |
|---|---|
| 找不到匹配的 distribution | BearAgent 是否已经发布，以及当前解释器是否为 Python 3.12 |
| 安装成功但找不到 `bearagent` | 是否激活了安装该包的虚拟环境；也可先运行 `python -m bearagent` |
| 命令存在但功能比文档少 | `bearagent --version` 是否对应包含该功能的发布版本 |
| 下载到了意外项目 | PyPI 项目所有者、项目链接和 release hash 是否与官方发布记录一致 |

`pip install` 的解析和安装阶段见
[pip 官方 install 文档](https://pip.pypa.io/en/stable/cli/pip_install/)。维护者怎样构建和上传 package，
继续阅读[怎样把 BearAgent wheel 发布到 PyPI](/BearAgent/zh-cn/development/publish-python-package/)。
