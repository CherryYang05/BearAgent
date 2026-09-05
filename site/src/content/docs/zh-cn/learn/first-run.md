---
title: 第一次运行：读一份文档
description: 初始化配置，运行一个小任务，再亲自核对文件与执行记录。
bearStatus: mixed
sourceRefs:
  - F-0020
  - F-0005
  - F-0017
  - ADR-0018
---

这一节只完成一件事：让 BearAgent 阅读一份文档，把简介写到 `outputs/intro.md`，再由你检查结果。
你只需要会打开终端、切换目录和编辑文本文件。暂时不用理解 SQLite、Reducer 或协议 adapter。

以下步骤适用于包含 `init` 命令的新版源码。旧版本若没有这个命令，可使用
[配置参考](https://github.com/CherryYang05/BearAgent/blob/main/docs/reference/configuration.md)的手工模板路径。

## 1. 安装并站在同一个目录里

准备 Git 和 [uv](https://docs.astral.sh/uv/) 后，在终端依次执行：

```console
git clone https://github.com/CherryYang05/BearAgent.git
cd BearAgent
uv python install 3.12
uv sync --all-groups --locked
uv run bearagent doctor
```

看到 `Status: ok` 表示 Python 环境满足要求。它还没有连接模型，也没有检查 API key。
下面的命令都在这个 `BearAgent` 目录执行。它就是这次的工作区，文件路径从这里开始计算。

## 2. 只初始化一次

```console
uv run bearagent init
```

命令建立两个 JSON 文件和一份数据目录的 Git 忽略规则。重复执行会保留现有文件。

| 文件 | 你用它决定什么 | 第一次是否需要编辑 |
|---|---|---|
| `data/config.json` | 连接哪个模型服务 | 需要填写服务信息 |
| `data/p1-run-profile.json` | Agent 的说明、工具和运行上限 | 小任务先使用生成的默认值 |

用文本编辑器打开 `data/config.json`。向你使用的模型服务确认 `protocol`、`base_url`、`api_key` 与
模型 ID；把模型 ID 同时填入 `models[0].model_id` 和 `default_model`。第一次保留 `provider_id: primary`。
三个协议值和字段示例见[配置一次模型服务](/zh-cn/learn/configure-model-service/)。

初始化不会连接服务，也不会替你填写密钥。只有稍后执行 `run` 才会向选中的模型服务发送请求，可能
产生费用。默认限制为 8 次模型、16 次 Tool、80,000 tokens 和 120 秒的新调用调度窗口；费用尚未定价，
真实账单限额需要在服务方设置。单次调用已经开始后，仍按自己的 timeout 结束。

## 3. 先检查配置，再运行

```console
uv run bearagent doctor --check-config
```

看到 `Status: ok` 表示本地配置结构、服务引用、工具与启动预算检查通过。检查不会创建数据库，也
不会测试服务是否在线；key 无效、余额不足或协议不兼容仍可能在真正调用时出现。

```console
uv run bearagent run "阅读 docs/index.md，把项目简介写到 outputs/intro.md"
```

这一次用户请求称为一个 **Run**。屏幕会先给出 Run ID，随后显示状态、回答和可能生成的文件。
不要预期每个模型都采取同样的步骤；先查看实际输出，再判断任务是否完成。

## 4. 亲自核对三个结果

1. 打开 `outputs/intro.md`：文件是否存在，内容是否确实来自输入资料？
2. 用刚才屏幕上的 ID 查看记录，命令中的 `RUN_ID` 要替换成实际值：

   ```console
   uv run bearagent run inspect RUN_ID
   uv run bearagent run events RUN_ID
   ```

3. 在 Event 中找到模型调用、文件读取和写入的记录。每次被跟踪的模型或工具操作称为 **Activity**；
   每条已经保存的记录称为 **Event**。它们帮助你核对执行，不替你评价总结写得是否正确。

`succeeded` 表示模型给出了终态回答，不能单独证明目标文件和内容达标。Artifact 显示的 hash 是写入
完成时记录的值；如果用户后来改了文件，历史记录不会自动改变。

## 5. 没成功时，先保留证据

| 看到什么 | 下一步 |
|---|---|
| 配置缺失或非法，还没有 Run ID | 执行 `init`，检查 config，再执行 `doctor --check-config` |
| `budget_exhausted` | 用 `inspect` 查看记录；调整 profile 后启动的是一个新 Run |
| `provider_authentication` 或 `provider_protocol_error` | 检查密钥、服务协议和服务文档；不会自动换服务 |
| `workspace_path_denied` | 确认输入是普通工作资料，不是 `data/`、`.git/`、`.env*` 或自定义 Runtime 文件 |
| 进程退出，查询仍显示 `running` | 保留数据库与输出文件；P1 不能自动续跑，也不能根据缺少完成 Event 判断文件没写过 |

资料默认在 `data/bearagent.db` 与 `outputs/`。工作区文件可能发给你配置的远程模型，因此“本地优先”
描述的是记录与产物的位置，不代表模型推理一定离线。不要把普通输入文件当作敏感数据保险箱。

现在你已经见过运行、产物和记录。下一节[一次文件任务的完整链路](/zh-cn/learn/agent-loop-file-task/)
解释谁决定下一步、谁真正打开文件，以及为什么这些职责要分开。需要查某个选项时，再打开
[完整命令行手册](/zh-cn/guides/cli/)。

本文新增的初始化与配置保护对应 F-0020，本地实现已验证；正式交付状态以 Feature Spec 为准。
