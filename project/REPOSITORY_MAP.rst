仓库文件职责
============

本文件说明每个主要路径当前承担什么职责，以及哪些内容属于未来预留。新增、删除或改变文件职责时必须同步更新。

状态说明
--------

``active``
   当前已经参与仓库运行或约束。

``incomplete``
   当前已使用，但关键内容仍未补齐。

``reserved``
   为已经确定的未来流程预留，当前不会主动执行。

根目录
------

``AGENTS.md`` — active
   所有新对话和新 Agent 的第一入口。保存读取顺序、当前阶段、准入条件和状态维护要求。

``README.rst`` — active
   面向仓库使用者的简要说明和本地命令。它不是完整的 Agent 接续文件。

``pyproject.toml`` — active
   固定 Python 3.12、Sphinx、doc8、pytest、ruff 和 uv 的基础依赖与工具配置。

``sources.lock`` — incomplete
   固定外部源码和规范版本。Linux 条目目前只有仓库地址，version 与 exact commit 仍为空，因此源码级文章保持 blocked。

``release-manifest.toml`` — reserved
   定义未来公共 release 快照允许导出的白名单。当前私有仓库不发布 Pages，该文件暂时只用于保持发布边界稳定。

``.gitignore`` — active
   排除虚拟环境、缓存、Sphinx 构建输出和 release 临时目录。

Agent 规则
----------

``.agents/skills/source-first-technical-book/SKILL.md`` — active
   章节生产的详细执行协议。仅在问题、实验、源码路径和 RST 生产阶段读取。项目接续仍由根 ``AGENTS.md`` 和 ``project/`` 状态文件负责。

项目状态
--------

``project/STATE.rst`` — active
   保存当前阶段、已完成事项、blocker 和下一步。每次有意义的工作后都要更新。

``project/DECISIONS.rst`` — active
   保存跨对话长期决策，防止新 Agent 重新推翻已经确定的仓库方向。

``project/REPOSITORY_MAP.rst`` — active
   保存文件职责和预留功能，解决“文件已经创建，后续 Agent 不知道为什么存在”的问题。

Sphinx 文档
-----------

``docs/conf.py`` — active
   Sphinx 基础配置。当前保持离线安全，不拉取外部 intersphinx inventory。

``docs/index.rst`` — active
   Sphinx 根文档和 toctree 入口。

``docs/architecture.rst`` — active
   说明问题、实验、来源、正文、验证和发布之间的整体关系。未来可进入公共 release。

``docs/books/index.rst`` — active
   技术书目录入口。

``docs/books/linux-kernel/index.rst`` — incomplete
   Linux Kernel 书籍入口。当前只展示 blocked 状态和首个候选问题。

``docs/books/linux-kernel/reading-contract.rst`` — active
   规定 Linux 书的 source contract、实验规则、源码路径规则和写作顺序。它是书籍级规则，不是正式章节。

实验
----

``labs/README.rst`` — active
   定义每个章节实验目录的标准结构和独立运行要求。

``labs/<book>/<chapter>/`` — reserved
   正式实验位置。当前尚未创建第一个 Linux lab，因为 source contract 与验证环境还未确定。

Manifest
--------

``manifests/books/linux-kernel.toml`` — incomplete
   保存 Linux 书籍范围、状态、首个问题和 source contract。当前 status 为 blocked。

``manifests/chapters/README.rst`` — active
   定义 chapter manifest 的字段和状态机。

``manifests/chapters/<chapter>.toml`` — reserved
   每篇正式章节的证据与验证状态。第一个 lab 建立后再创建，不提前制造空文件。

模板
----

``templates/chapter.rst`` — reserved
   正式章节的 RST 骨架。它不参与 Sphinx 构建，也不能在证据不足时直接复制生成文章。

工具
----

``tools/audit_chapter.py`` — active
   检查正式章节中的 Markdown fenced code block、禁用铺垫语和完全重复段落，并要求章节包含代码、命令输出或 doctest 证据。

``tools/export_release.py`` — reserved
   未来根据 ``release-manifest.toml`` 生成 ``dist/release/`` 公共快照。当前不会推送任何公共仓库。

GitHub Actions
--------------

``.github/workflows/verify.yml`` — active
   每次推送 ``main`` 时执行 ruff、RST 审计、doc8、已有 lab 测试和 Sphinx warnings-as-errors 构建。它只做验证，不部署 Pages。

未来允许新增的内容
------------------

以下内容应当按实际需要创建，不提前堆空目录：

* ``labs/linux-kernel/read-enters-vfs/``：source contract 确定后的首个实验；
* ``manifests/chapters/read-enters-vfs.toml``：首个实验建立后的章节状态；
* ``docs/books/linux-kernel/chapter-*.rst``：证据齐全后的正式正文；
* 公共 release 仓库配置：稳定内容准备发布时再创建；
* Pages workflow：只存在于未来公共仓库。
