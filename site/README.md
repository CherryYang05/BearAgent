# BearAgent 中文学习书与开发者文档

`site/` 是 BearAgent 的中文学习和开发者网站。工程事实仍由仓库中的 `docs/`、代码和测试确认；
这里用连续例子解释这些事实，并明确区分已经实现和未来计划。

目标公开地址是 `https://cherryyang05.github.io/BearAgent/`。2026-08-25 复核时该地址与仓库 Pages
API 仍返回 404；本地构建成功不等于已经上线。代码合并后还需在仓库 Pages 设置中选择 GitHub
Actions 作为 Source，并在无登录浏览器中完成公开验收。

## 本地运行

需要 Node.js 22.12+ 和 npm 9.6.5+。在仓库根目录执行：

```powershell
npm --prefix=site ci
npm run dev --prefix=site
```

访问 `http://localhost:4321/BearAgent/zh-cn/`。本地也保留 `/BearAgent/`，这样可以提前发现只在
GitHub Pages 仓库子路径下才会出现的错误链接。

验证生产构建和本地搜索：

```powershell
npm run build --prefix=site
npm run preview --prefix=site
```

`site/dist/` 是可重新生成的构建产物，不提交 Git。

## 发布

`.github/workflows/deploy-docs.yml` 在 `site/` 变更进入 `main` 后构建并发布 GitHub Pages。普通 PR
仍只执行 CI 构建，不会部署。workflow 不需要仓库 secret，只使用 GitHub Pages 的短期身份。

## 内容怎样像一本书一样分工

- 序章：先回答 BearAgent 是什么、现在能做什么；
- 第一部：独立 CLI 手册、模型配置和一次真实 Run；
- 第二部：Model、Context、Tool、Runtime、Event、状态与预算；
- 第三部：adapter、Policy、workspace 路径和原子输出；
- 第四部：稳定架构关系与 P1 取舍；
- 第五部：沿实际调用链进入代码和测试；
- 第六部：行业现状、研究问题和 BearAgent Roadmap；
- 附录：术语、来源、构建、发布和历史快照。

CLI 精确契约仍由 F-0005、Schema、代码和测试确认；使用手册负责把它们组织成可执行流程。每个
Feature 完成时都要检查以上相关页面。不要复制 Spec 原文，也不要用机械术语替换代替重写。

`public/images/*-4k.jpg` 是 GPT Image 生成后以高质量重采样入库的 3840×2160 插画。它们只负责建立
章节印象；精确流程使用 Mermaid。新增图片必须写 alt，并检查桌面和 390px 手机裁切。
