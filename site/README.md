# BearAgent 文档站

`site/` 是 BearAgent 的中文学习和开发者网站。工程事实仍由仓库中的 `docs/`、代码和测试确认；
这里用连续例子解释这些事实，并明确区分已经实现和未来计划。

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

## 内容怎样分工

- `learn/`：从一次 Agent 任务出发解释原理和术语；
- `architecture/`：解释 Runtime、port、adapter 和长期边界；
- `development/`：提供代码入口、修改约束和验证命令；
- `project/`：说明产品方向、阶段顺序和当前实现状态。

每个 Feature 完成时都要检查以上相关页面。不要复制 Spec 原文，也不要用机械术语替换代替重写。
