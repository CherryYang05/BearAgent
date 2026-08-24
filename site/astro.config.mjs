import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import mermaid from 'astro-mermaid';

export default defineConfig({
  site: 'https://cherryyang05.github.io',
  base: '/BearAgent',
  integrations: [
    mermaid({
      autoTheme: true,
      enableLog: false,
      mermaidConfig: {
        securityLevel: 'strict',
        flowchart: { curve: 'basis' },
      },
    }),
    starlight({
      title: 'BearAgent Docs',
      description: '让个人 Agent 在本地可靠地完成长任务',
      disable404Route: true,
      logo: {
        src: './src/assets/bearagent-logo.png',
        alt: 'BearAgent',
      },
      defaultLocale: 'zh-cn',
      locales: {
        'zh-cn': {
          label: '简体中文',
          lang: 'zh-CN',
        },
      },
      lastUpdated: true,
      customCss: ['./src/styles/custom.css'],
      sidebar: [
        {
          label: '开始',
          items: [
            { label: 'BearAgent 要解决什么问题', slug: 'start/what-is-bearagent' },
            { label: '现在实现到了哪里', slug: 'project/status' },
          ],
        },
        {
          label: '使用 BearAgent',
          items: [
            { label: 'P1 命令行完整手册', slug: 'guides/cli' },
            { label: '从命令行运行并检查 Run', slug: 'learn/run-inspect-events' },
          ],
        },
        {
          label: 'P1 主学习路线',
          items: [
            { label: '先会用，再看懂', slug: 'learn' },
            { label: '一项 Agent 任务怎样运转', slug: 'learn/agent-basics' },
            { label: '一次文件任务怎样走完整条链', slug: 'learn/agent-loop-file-task' },
            { label: '状态和预算怎样计算', slug: 'learn/runtime-state-and-budgets' },
            { label: '逐条读懂一次 Run', slug: 'learn/run-event-reducer-walkthrough' },
            { label: '持久事实与安全恢复', slug: 'learn/durable-events' },
          ],
        },
        {
          label: 'P1 边界深挖',
          items: [
            { label: '为什么模型需要独立边界', slug: 'learn/model-provider-boundary' },
            { label: '配置模型服务并重复使用', slug: 'learn/configure-model-service' },
            { label: 'Tool 请求为什么要过四道检查', slug: 'learn/tool-execution-boundary' },
            { label: 'Windows 和 Unix 路径怎样统一', slug: 'learn/workspace-read-boundary' },
            { label: '原子输出怎样保护旧文件', slug: 'learn/atomic-output-boundary' },
            { label: '失败后先问哪三个问题', slug: 'learn/recovery-authority-isolation' },
          ],
        },
        {
          label: 'BearAgent 架构',
          items: [
            { label: '先看 BearAgent 怎样分工', slug: 'architecture' },
            { label: '一次请求怎样穿过 BearAgent', slug: 'architecture/runtime-flow' },
            { label: 'P1 为什么这样设计', slug: 'architecture/p1-decisions' },
            { label: '可靠性与安全边界', slug: 'architecture/reliability-boundaries' },
            { label: '模块之间怎样交换数据', slug: 'architecture/domain-contracts' },
          ],
        },
        {
          label: '开发者文档',
          items: [
            { label: '怎样顺着代码读懂 BearAgent', slug: 'development' },
            { label: '从数据边界开始读代码', slug: 'development/domain-contracts' },
            { label: '沿 Event 读懂状态与预算', slug: 'development/run-reducer-and-budgets' },
            { label: '从一次 append 读持久化', slug: 'development/sqlite-event-store' },
            { label: '跟一次流式调用读模型 adapter', slug: 'development/model-provider' },
            { label: '跟一次 ToolRequest 读执行边界', slug: 'development/tool-execution-boundary' },
            { label: 'F-0007：workspace 只读 Tool', slug: 'development/workspace-read-tools' },
            { label: 'F-0008：原子输出与 Artifact', slug: 'development/atomic-output-artifacts' },
            { label: 'F-0016：有界 Agent Loop', slug: 'development/agent-loop' },
            { label: 'F-0005：生产 CLI 与查询', slug: 'development/run-cli' },
            { label: '把 wheel 发布到 PyPI', slug: 'development/publish-python-package' },
            { label: '代码变了，站点怎样跟着变', slug: 'development/feature-documentation' },
            { label: '本地运行文档站', slug: 'guides/local-docs' },
          ],
        },
        {
          label: '扩展阅读',
          items: [
            { label: 'Agent 现在发展到哪一步', slug: 'learn/agents-today' },
            { label: 'Agent 仍然难在哪里', slug: 'learn/open-problems' },
            { label: '历史：F-0016 前的快照', slug: 'learn/before-agent-loop' },
            { label: 'PyPI 发布与安装状态', slug: 'guides/install-from-pypi' },
            { label: '术语表', slug: 'reference/glossary' },
            { label: '参考资料与阅读路线', slug: 'reference/sources' },
          ],
        },
        {
          label: '项目',
          items: [
            { label: 'BearAgent 按什么顺序完成', slug: 'project/milestones' },
            { label: '为什么做 BearAgent', slug: 'project/positioning' },
          ],
        },
      ],
    }),
  ],
});
