---
title: "ADR-0019: a successful main push deploys docs through a restricted SSH identity"
status: accepted
date: 2026-09-05
decision_owners: [CherryYang05]
supersedes: null
superseded_by: null
---

# ADR-0019：main 推送成功后使用受限身份发布静态文档

## 冲突

Git 没有标准 `post-push` 客户端 hook。`pre-push` 发生在 GitHub 接受提交之前，网络失败也可能让线上
版本先于仓库变化。常驻 Astro preview server 又为纯静态站增加 Node 进程、4321 端口和重启故障。

## 决定

- `main` 的 GitHub `push` 事件触发文档 workflow；PR 与功能分支不覆盖 production；
- workflow 锁定安装并构建 `site/dist/`，之后才通过 SSH 把压缩包写入服务器发布脚本的标准输入；
- GitHub Secret 只保存独立部署私钥，仓库固定服务器公开 Ed25519 host key，禁用运行时 `ssh-keyscan`；
- 对应公钥在服务器 `authorized_keys` 中使用 forced command，并禁用 PTY、转发和 agent/X11 forwarding；
- root 管理的入口在 `sudo` 清理环境前拒绝非空 `SSH_ORIGINAL_COMMAND`，再把标准输入交给发布脚本；
- root 管理的脚本限制上传与解压大小，拒绝绝对路径、`..`、链接和特殊文件，检查关键页面后原子换目录；
- 健康检查失败恢复上一目录。历史备份不由 workflow 自动删除，避免错误清理扩大故障。

部署身份只能触发这个固定脚本，不能选择命令或发布目录。服务器上的 1Panel/OpenResty 继续终止 TLS
并直接提供静态文件；不启动 Astro 服务，不向 GitHub 暴露 1Panel、模型或 Runtime 凭据。

## 影响与回退

GitHub Actions 和服务器成为文档发布链的一部分。GitHub 服务、SSH 或健康检查失败时，workflow 失败，
当前线上目录保持不变或自动恢复。撤销自动发布时，删除 GitHub Secret 与对应 forced-command 公钥，
再禁用 workflow；已发布静态文件仍可由 OpenResty 提供。

host key 轮换必须先由已有可信 SSH 通道核对，再修改仓库中的 known-hosts 文件。部署私钥轮换时先安装
新的受限公钥、更新 Secret、运行一次手动 workflow，最后移除旧公钥。
