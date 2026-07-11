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

``.agents/skills/source-first-technical-book/SKILL.md`` 保留为章节生产的详细流程。它不承担项目状态存储，也不能替代 ``AGENTS.md``、``project/STATE.rst``、固定内容计划和 manifests。

D-008：当前不写正式文章
-----------------------

状态：accepted

基础目录存在不代表具备写作条件。frozen plan、source contract、最小实验、真实输出、源码符号验证和 chapter manifest 齐全后，才能创建正式章节。

D-009：证据优先
---------------

状态：accepted

章节从可运行代码、真实输出、固定源码和最短调用路径出发。解释性文字不能替代缺失证据。

D-010：内容计划在书籍开始前固定
-------------------------------

状态：accepted

一本书开始生产前，必须一次性确定范围、Part、全部章节 ID、问题、顺序、学习结果、前置依赖和证据类型，并将 plan 状态设置为 ``frozen``。每次生成内容时不重新选题。

旧 Roadmap 只在规划阶段作为主题库存。它不能在正式生产阶段临时增加、删除或重排章节。

D-011：Narrative 不进入本仓库
------------------------------

状态：accepted

文学、电影、电视剧和游戏编年史等 Narrative 内容继续留在旧仓库，不进入 ``techBook`` 的技术书生产流程。

D-012：Linux Kernel 第一卷范围
-----------------------------

状态：accepted

首本书为 ``Linux Kernel 源码阅读：ARM64 启动、初始化与 VFS``。第一卷按固定顺序覆盖 ARM64 启动入口、MMU 与虚拟地址切换、``start_kernel``、initcall、用户空间 init、``read()`` 系统调用与 VFS。

第一章为 ``LK-BOOT-001``：“ARM64 Linux 内核镜像从哪个入口开始执行？” ``read()`` 与 VFS 位于第一卷后半部分。

D-013：每次运行只做执行条件检查
---------------------------------

状态：accepted

每次 Agent 运行只读取 frozen plan，定位顺序最靠前且未完成的章节，并检查前置依赖、source contract、实验和证据。该检查只决定能否执行当前章节，不产生新的选题。

当前章节被 blocked 时默认停止。修改计划必须增加 ``plan_version``、记录原因，并由用户明确改变范围或由实际证据证明原计划错误。
