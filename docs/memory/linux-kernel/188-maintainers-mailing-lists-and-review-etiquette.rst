第188章：MAINTAINERS、邮件列表与 Review 礼仪
===========================================

核心知识点
----------

补丁必须进入正确维护边界
   收件人判断从修改路径和影响范围开始。``MAINTAINERS``、子系统文档、Git History 与公共接口影响共同决定 Maintainer、Reviewer 和 Mailing List。

``get_maintainer.pl`` 只生成候选
   脚本根据路径、维护规则和历史给出地址集合，作者仍需识别跨子系统接口、文档、Binding、UAPI 和前一版参与者，形成最终 ``To`` 与 ``Cc``。

普通补丁采用纯文本邮件
   ``git format-patch`` 生成 Patch 文件，``git send-email`` 负责投递。HTML、富文本、自动换行和附件处理都可能破坏 Diff 或线程关系。

Series 需要清晰的层级
   Cover Letter 说明整体问题、拆分、依赖和测试；每枚 Patch 仍需自包含。中间 Commit 应保持可构建、可运行和可 Bisect。

Review 回复应绑定具体评论
   Inline Reply 保留必要上下文，并逐项说明已修改、未修改的理由或需要继续讨论的部分。简单回复 ``Done`` 不能解释 ABI、并发和错误路径问题。

新版应修改原 Commit
   Reroll 时应把修正折回对应逻辑 Commit，重新生成 v2、v3，并提供具体 Changelog；不能只手工编辑邮件附件或追加“修复上一版”的尾部 Patch。

Review Tag 绑定具体版本
   ``Reviewed-by``、``Tested-by`` 和 ``Acked-by`` 只能来自提供者本人。算法、ABI、锁和生命周期发生实质变化后，应重新判断旧 Tag 是否仍有效。

线程和公开归档是状态依据
   客户端显示发送成功不等于列表已收到。应检查公开归档中的 Message-ID 和 Thread；合理跟进应保留原线程并避免高频重复发送。

关键路径
--------

确定收件人：

::

   修改路径与影响范围
   → MAINTAINERS
   → get_maintainer.pl
   → Git History 与子系统文档复核
   → To / Cc

邮件迭代：

::

   逻辑 Commits
   → format-patch
   → send-email
   → 公开归档
   → Inline Review
   → 修改原 Commits
   → v2 / v3 + Changelog

概念辨析
--------

* **当前维护责任与历史作者**：``MAINTAINERS`` 描述当前边界；历史作者只提供过去的实现背景。
* **候选收件人与最终路由**：脚本给出候选；最终收件人还取决于接口影响、子系统规则和跨树依赖。
* **Cover Letter 与 Commit Message**：前者解释整个 Series；后者必须独立解释单枚逻辑变化。
* **Inline Reply 与 Top-post**：Inline Reply 把答复绑定到具体问题；Top-post 容易切断评论与回答的对应关系。
* **新版自包含与版本演进**：当前版本应独立可读，Changelog 和原线程负责保存相对旧版的变化。
* **邮件已发送与已进入归档**：发送动作只证明客户端投递；公开归档中的线程才证明列表可见。

本章结论
--------

内核邮件工作流通过路径驱动的路由、纯文本 Patch、逐项 Review 回复和可追踪版本迭代，把本地提交转化为社区能够共同理解和维护的公开设计记录。