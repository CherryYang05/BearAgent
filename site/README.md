# BearAgent 文档站

`site/` 是 BearAgent 的中文学习和开发者网站。工程事实仍由仓库中的 `docs/`、代码和测试确认；
这里用连续例子解释这些事实，并明确区分已经实现和未来计划。

公开地址：`https://cherryyang05.github.io/BearAgent/`。代码合并后仍需在仓库 Pages 设置中选择
GitHub Actions 作为 Source，首次部署成功后该地址才会生效。

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

## 内容怎样分工

- `guides/cli.md`：独立维护 P1 的安装、配置、命令、退出码和排错；
- `learn/`：按“先会用，再看懂”的顺序解释一次 Run；
- `architecture/`：解释 Runtime、port、adapter、关键取舍和长期边界；
- `development/`：提供代码入口、修改约束和验证命令；
- `project/`：说明产品方向、阶段顺序和当前实现状态。

CLI 精确契约仍由 F-0005、Schema、代码和测试确认；使用手册负责把它们组织成可执行流程。每个
Feature 完成时都要检查以上相关页面。不要复制 Spec 原文，也不要用机械术语替换代替重写。
