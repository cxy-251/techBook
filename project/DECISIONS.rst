长期决策
========

本文件保存跨对话必须继续遵守的长期决策。新 Agent 不得仅凭聊天记忆修改这些决策；修改时要记录新决策及原因。

D-001：私有开发仓库
-------------------

状态：accepted

``cxy-251/techBook`` 是私有开发仓库，保存正文、实验、内部状态、Skill、审计工具和来源锁定信息。

D-002：只使用 main
------------------

状态：accepted

当前所有工作直接提交到 ``main``。不创建功能分支和 PR，除非用户以后明确改变该规则。

D-003：RST 与 Sphinx
-------------------

状态：accepted

正式技术书使用 reStructuredText。Sphinx 负责构建、交叉引用、``literalinclude``、doctest 和 warnings-as-errors 验证。

D-004：暂不发布 Pages
---------------------

状态：accepted

普通 GitHub 用户的私有仓库不作为 Pages 发布源。内容稳定后建立独立公共 release 仓库，由公共仓库发布 GitHub Pages。

D-005：私有仓库与公共仓库分离
--------------------------------

状态：accepted

私有仓库持续修改。公共仓库只接收通过验证的稳定快照。公共 release 由 ``release-manifest.toml`` 白名单控制。

D-006：AGENTS 是接续入口
-------------------------

状态：accepted

任何新对话和新 Agent 都从根目录 ``AGENTS.md`` 恢复上下文。聊天记录不属于项目依赖。

D-007：Skill 是详细流程
------------------------

状态：accepted

``.agents/skills/source-first-technical-book/SKILL.md`` 保留为章节生产的详细流程。它不承担项目状态存储，也不能替代 ``AGENTS.md``、``project/STATE.rst`` 和 manifests。

D-008：当前不写正式文章
-----------------------

状态：accepted

基础目录存在不代表具备写作条件。source contract、最小实验、真实输出、源码符号验证和 chapter manifest 齐全后，才能创建正式章节。

D-009：证据优先
---------------

状态：accepted

章节从可运行代码、真实输出、固定源码和最短调用路径出发。解释性文字不能替代缺失证据。

D-010：Roadmap 可重构
---------------------

状态：accepted

Roadmap 只保存候选问题。允许删除、合并、拆分和重新排序，不按预设章节数量填充内容。

D-011：Narrative 不进入本仓库
------------------------------

状态：accepted

文学、电影、电视剧和游戏编年史等 Narrative 内容继续留在旧仓库，不进入 ``techBook`` 的技术书生产流程。

D-012：首本书为 Linux Kernel
-----------------------------

状态：accepted

首本候选书是 Linux Kernel 源码阅读。首个候选问题为“用户态 ``read()`` 如何进入 VFS”。当前仍等待 source contract 与实验环境确定。
