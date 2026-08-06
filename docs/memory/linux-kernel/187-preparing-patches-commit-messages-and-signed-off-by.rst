第187章：准备 Patch、Commit Message 与 Signed-off-by
===================================================

核心知识点
----------

一个 Patch 表达一个逻辑变化
   逻辑边界由问题和对象关系决定，不由文件数或代码行数决定。修复、重构、格式整理、性能优化和新功能通常应拆开，使每个 Commit 可独立评审、回滚和 Bisect。

Commit Message 解释因果链
   Diff 说明代码如何变化；Commit Message 应说明触发条件、错误状态、根因、修复方法、影响范围以及哪些既有语义保持不变。

Subject 负责快速定位
   Subject 通常由子系统前缀、局部对象和明确动作组成，并使用简洁的祈使表达。``fix bug``、``update code`` 等标题无法支持邮件检索和历史阅读。

Body 必须自包含
   外部链接可以保存完整报告和讨论，正文仍应保留未来维护者理解问题所需的最小事实。Series 的 Cover Letter 不能替代单枚 Commit Message。

Trailer 表示不同责任
   ``Signed-off-by`` 表示依据 DCO 声明有权提交贡献；``Reviewed-by``、``Tested-by`` 和 ``Acked-by`` 表示特定版本上的评审或验证，不能由作者代替他人添加。

``Fixes:`` 必须指向引入缺陷的提交
   它用于回归定位、Stable 判断和历史追踪，不是普通“相关提交”。添加前应有源码历史、Bisect 或行为变化证据。

版本说明不属于永久历史
   ``Changes in v2``、测试补充和邮件说明通常放在 ``---`` 之后或 Cover Letter 中；最终 Commit Message 只保存完成后的问题与修复论证。

工具检查不能替代语义检查
   ``git diff --check``、``checkpatch.pl`` 和完整 ``git show`` 能发现格式及常见问题，仍无法证明并发、生命周期、ABI 和硬件语义正确。

关键路径
--------

形成逻辑 Patch：

::

   本地 Diff
   → 写出单句问题
   → 区分必要修复与无关变化
   → 拆分逻辑 Commits
   → 确认每个 Commit 可构建、回滚和 Bisect

组织 Commit Message：

::

   Subject：子系统 + 对象 + 动作
   → 触发条件与影响
   → 根因和被破坏的不变量
   → 修复方式与保持不变的语义
   → 测试和真实 Trailers

概念辨析
--------

* **一个逻辑变化与一个文件**：一个变化可以跨多个文件；单个文件也可能包含多个应拆分的问题。
* **Diff 与 Commit Message**：Diff 描述实现变化；Commit Message 保存问题、根因和修复理由。
* **Subject 与 Body**：Subject 用于快速识别；Body 保存完整因果链和边界。
* **``Signed-off-by`` 与 ``Reviewed-by``**：前者是 DCO 权利与责任声明；后者是对特定版本技术内容的认可。
* **``Fixes:`` 与相关历史**：``Fixes:`` 指向真正引入缺陷的 Commit；其它相关提交只能作为背景。
* **Checkpatch 通过与技术正确**：格式检查通过不代表对象生命周期、锁和 ABI 正确。

本章结论
--------

可上游评审的 Patch 必须把单一逻辑变化、自包含的因果说明和真实责任 Trailer 链整理成可评审、可回滚、可长期追踪的 Commit。