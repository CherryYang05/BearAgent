# BearAgent 中文学习书与开发者文档

`site/` 是 BearAgent 的中文学习和开发者网站。工程事实仍由仓库中的 `docs/`、代码和测试确认；
这里用连续例子解释这些事实，并明确区分已经实现和未来计划。

它是仓库中的静态文档展示站。当前交付包括本地开发、生产构建、预览和 main 推送后的自动发布；
线上版本位于 [docs.bearguin.cn](https://docs.bearguin.cn/zh-cn/)。仓库不保存部署私钥，只引用
GitHub Actions Secret `DOCS_DEPLOY_KEY`。

## 本地运行

需要 Node.js 22.12+ 和 npm 9.6.5+。在仓库根目录执行：

```powershell
npm --prefix=site ci
npm run dev --prefix=site
```

访问 `http://localhost:4321/zh-cn/`。

验证生产构建和本地搜索：

```powershell
npm run build --prefix=site
npm run preview --prefix=site
```

`site/dist/` 是可重新生成的构建产物，不提交 Git。

## 构建边界

普通 CI 会锁定安装依赖并构建站点，用来发现损坏的 Front Matter、路由、MDX、Mermaid 和搜索索引。
`.github/workflows/deploy-docs.yml` 只在 GitHub 接受 `main` 推送后发布；PR 和功能分支不会覆盖线上站点。
workflow 使用受限 SSH 身份发送构建包，服务器校验包后原子换目录，并在公网健康检查失败时恢复上一版。
1Panel/OpenResty 直接提供静态文件和 TLS，不需要常驻 Astro 服务。workflow 文件进入 `main` 前，自动触发
尚未生效；本地构建成功本身也不能证明线上已更新。

## 内容怎样像一本书一样分工

- 开始：先回答 BearAgent 是什么、现在能做什么；
- 第一步：独立 CLI 手册、模型配置和一次真实 Run；
- 第二步：Model、Context、Tool、Runtime、Event、状态与预算；
- 第三步：adapter、Policy、workspace 路径和原子输出；
- 第四步：稳定架构关系与 P1 取舍；
- 第五步：沿实际调用链进入代码和测试；
- 第六步：行业现状、研究问题和 BearAgent Roadmap；
- 查阅：术语、来源、构建、发布和历史快照。

CLI 精确契约仍由 F-0005、Schema、代码和测试确认；使用手册负责把它们组织成可执行流程。每个
Feature 完成时都要检查以上相关页面。不要复制 Spec 原文，也不要用机械术语替换代替重写。

`public/images/bearagent-recovery-cover-4k.webp` 是 GPT Image 生成后以高质量重采样入库的
3840×2160 章节插画。它只建立“意图—执行—证据—判断”的视觉印象，不承载精确标签。
`public/images/runtime-boundary.svg` 是可编辑、可用于论文和宣传材料的 3840×2160 矢量母版；同目录的
`runtime-boundary-4k.png` 是便于演示软件使用的 4K 导出。精确时序仍使用 Mermaid。新增图片必须写
alt，并检查桌面和 390px 手机裁切。
