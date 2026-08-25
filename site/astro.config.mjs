import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import mermaid from 'astro-mermaid';

export default defineConfig({
  integrations: [
    mermaid({
      autoTheme: true,
      enableLog: false,
      mermaidConfig: {
        securityLevel: 'strict',
        flowchart: { curve: 'basis', htmlLabels: true },
      },
    }),
    starlight({
      title: 'BearAgent',
      description: '从一次可检查的本地文件任务，学会设计可靠的 Agent Runtime',
      favicon: '/favicon.svg',
      disable404Route: true,
      logo: {
        light: './src/assets/bearagent-wordmark-light.svg',
        dark: './src/assets/bearagent-wordmark-dark.svg',
        alt: '',
        replacesTitle: true,
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
          label: '序章 · 先建立全局认识',
          items: [
            { label: 'BearAgent 要解决什么问题', slug: 'start/what-is-bearagent' },
            { label: '现在实现到了哪里', slug: 'project/status' },
            { label: '全书阅读地图', slug: 'learn' },
          ],
        },
        {
          label: '第一部 · 先亲手跑一次',
          items: [
            { label: '完整命令行手册', slug: 'guides/cli' },
            { label: '配置一次模型服务', slug: 'learn/configure-model-service' },
            { label: '运行、检查与读取 Event', slug: 'learn/run-inspect-events' },
          ],
        },
        {
          label: '第二部 · 看懂 Agent 运行',
          items: [
            { label: '一项 Agent 任务怎样运转', slug: 'learn/agent-basics' },
            { label: '一次文件任务的完整链路', slug: 'learn/agent-loop-file-task' },
            { label: '状态和预算怎样计算', slug: 'learn/runtime-state-and-budgets' },
            { label: '逐条读懂一次 Run', slug: 'learn/run-event-reducer-walkthrough' },
            { label: 'Event 为什么是事实来源', slug: 'learn/durable-events' },
          ],
        },
        {
          label: '第三部 · 理解安全边界',
          items: [
            { label: '模型为什么需要 adapter', slug: 'learn/model-provider-boundary' },
            { label: 'Tool 请求为什么过四道检查', slug: 'learn/tool-execution-boundary' },
            { label: '路径怎样留在 workspace', slug: 'learn/workspace-read-boundary' },
            { label: '为什么不能直接覆盖文件', slug: 'learn/atomic-output-boundary' },
            { label: '失败后先问哪三个问题', slug: 'learn/recovery-authority-isolation' },
          ],
        },
        {
          label: '第四部 · 拼出系统架构',
          items: [
            { label: '架构总览', slug: 'architecture' },
            { label: '一次请求怎样穿过 Runtime', slug: 'architecture/runtime-flow' },
            { label: 'P1 的关键设计决定', slug: 'architecture/p1-decisions' },
            { label: '可靠性与安全边界', slug: 'architecture/reliability-boundaries' },
            { label: '模块怎样交换数据', slug: 'architecture/domain-contracts' },
          ],
        },
        {
          label: '第五部 · 沿代码继续学习',
          items: [
            { label: '源码阅读路线', slug: 'development' },
            { label: '领域数据与 Schema', slug: 'development/domain-contracts' },
            { label: 'Reducer 与预算', slug: 'development/run-reducer-and-budgets' },
            { label: 'SQLite EventStore', slug: 'development/sqlite-event-store' },
            { label: '模型 Provider adapter', slug: 'development/model-provider' },
            { label: 'Tool 执行边界', slug: 'development/tool-execution-boundary' },
            { label: 'workspace 只读 Tool', slug: 'development/workspace-read-tools' },
            { label: '原子输出与 Artifact', slug: 'development/atomic-output-artifacts' },
            { label: '有界 Agent Loop', slug: 'development/agent-loop' },
            { label: '生产 CLI 与查询', slug: 'development/run-cli' },
          ],
        },
        {
          label: '第六部 · 走向研究与扩展',
          items: [
            { label: 'Agent 今天能做什么', slug: 'learn/agents-today' },
            { label: 'Agent 仍然难在哪里', slug: 'learn/open-problems' },
            { label: 'BearAgent 的阶段路线', slug: 'project/milestones' },
            { label: '为什么做 BearAgent', slug: 'project/positioning' },
          ],
        },
        {
          label: '附录 · 查阅与贡献',
          items: [
            { label: '术语表', slug: 'reference/glossary' },
            { label: '参考资料与阅读路线', slug: 'reference/sources' },
            { label: '本地运行文档站', slug: 'guides/local-docs' },
            { label: '代码变更怎样同步文档', slug: 'development/feature-documentation' },
            { label: '构建和发布 Python 包', slug: 'development/publish-python-package' },
            { label: 'PyPI 安装状态', slug: 'guides/install-from-pypi' },
            { label: '历史：Agent Loop 之前', slug: 'learn/before-agent-loop' },
          ],
        },
      ],
    }),
  ],
});
