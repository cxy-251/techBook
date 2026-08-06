第188章：MAINTAINERS、邮件列表与 Review 礼仪
===========================================

本章必须记住
------------

#. 内核补丁必须进入正确维护边界和邮件线程，才能获得有效 Review。
#. 收件人判断从修改文件路径和影响范围开始。
#. ``MAINTAINERS`` 是源码树中的维护责任索引。
#. ``M:`` 通常表示 Maintainer，``R:`` 表示 Reviewer，``L:`` 表示 Mailing List。
#. ``F:`` 表示匹配路径，``X:`` 表示排除范围，``T:`` 可给出维护树。
#. 字段和维护状态随版本变化，必须使用目标源码树中的当前文件。
#. 一个修改可能同时匹配具体驱动、通用子系统、文档和公共接口多个条目。
#. 修改公共 Header、UAPI、Binding 或通用 Helper 时，不能只发送给最具体文件的维护者。
#. ``scripts/get_maintainer.pl`` 根据路径、``MAINTAINERS`` 和 Git History 生成候选收件人。
#. 脚本输出是候选集合，不是最终权责结论。
#. Git History 用于找到近期处理过相似改动的人，不能替代当前维护责任。
#. 子系统文档可能规定专用列表、前缀、基线、测试和维护树要求。
#. 普通补丁应让相关 Maintainer、Reviewer 和公开列表都能看到。
#. 只私发 Maintainer 会失去公开归档和社区 Review，除非流程明确要求其它方式。
#. 发错列表会延迟 Review，也会让缺少上下文的人承担噪声。
#. Linux 内核普通 Patch 以纯文本邮件为主要投递形式。
#. 纯文本允许 Reviewer 逐行引用 Diff，并让讨论进入长期归档。
#. HTML、富文本、自动换行和附件可能破坏 Patch 内容。
#. ``git format-patch`` 把本地 Commit 转换为邮件 Patch 文件。
#. ``git send-email`` 把 Patch 文件发送给维护者和列表。
#. 前者负责生成材料，后者负责投递；二者都不证明设计正确。
#. 单 Patch Subject 常带 ``[PATCH]``；Series 中带 ``[PATCH 1/N]`` 等编号。
#. 新版本应带 ``v2``、``v3`` 等 Reroll 标记。
#. 版本号只表示投递迭代，不表示技术质量自动提高。
#. 多 Patch Series 通常需要 Cover Letter 说明整体问题、设计和拆分顺序。
#. Cover Letter 解释 Series 为什么存在、各 Patch 如何协作以及怎样测试。
#. 每枚 Commit Message 仍必须自包含，不能依赖 Cover Letter 才能理解。
#. ``0/N`` Cover Letter 是整体讨论入口，``1/N`` 至 ``N/N`` 是具体实现评审入口。
#. Reviewer 可在 Cover Letter 下讨论整体设计，在具体 Patch 下讨论实现细节。
#. Series 中每枚 Patch 都应是一个逻辑变化，并保持中间状态可构建、可运行和可 Bisect。
#. Cover Letter 应说明基础树、依赖关系、测试矩阵、已知限制和版本变化。
#. 跨子系统依赖必须明确，不能假设维护者会自动推断合并顺序。
#. ``Changes in v2`` 等版本说明通常放在 ``---`` 后或 Cover Letter 中。
#. 版本说明服务当前 Review，通常不进入最终 Commit Log。
#. Changelog 应具体说明哪些 Patch、路径和设计发生变化。
#. “Address review comments”不能让 Reviewer判断意见是否真正闭合。
#. 新版必须自包含，使后来加入的 Reviewer 只读当前版本也能理解。
#. 新版也要保留演进线索，使旧 Reviewer 能快速检查上一轮意见。
#. Reroll 前应修改原 Commits，再重新生成 Patch，而不是只手工修改邮件附件。
#. 手工邮件内容与 Git Commit 不一致会破坏可重复生成和后续入树。
#. 每一版都应重新检查收件人，因为 Patch 拆分和影响范围可能改变。
#. 参与过前一版 Review 的人员通常应继续收到新版。
#. 发送前应检查 Subject、编号、收件人、Thread、Diffstat 和正文格式。
#. 初次配置邮件工具时，应先给自己发送测试 Patch 验证纯文本和换行。
#. 邮件投递后应确认它进入预期公开归档。
#. Lore 中找不到邮件时，不能假设列表和维护者已经收到。
#. Message-ID 是邮件线程的重要标识，可用于后续关联讨论。
#. Review 回复应在对应引用下直接回应，而不是只在顶部写一段总结。
#. Inline Reply 应保留理解当前答复所需的最小上下文。
#. 过度引用整封邮件会降低可读性，删除全部上下文也会失去问题对应关系。
#. 对每条实质评论应说明：已修改、另行处理、保留原方案及理由，或需要继续讨论。
#. “Done”“Fixed”不足以解释并发、ABI、错误路径和兼容性问题。
#. 不同意 Reviewer 时，应给出对象、状态、路径、测量或文档依据。
#. Review 是设计验证过程，不是简单命令执行。
#. Reviewer 的疑问可能暴露 Commit Message、自描述性或结构不清，即使代码最终无需修改。
#. 如果设计只能靠作者口头解释，说明维护成本仍然过高。
#. Review 评论通常检查 ABI、锁、生命周期、错误回滚、硬件兼容和测试证据。
#. 作者应先把评论映射到真实对象，再决定改代码、补说明、拆 Patch 或增加测试。
#. 不应为获得 Tag 而接受明知错误的修改，也不应把技术分歧转成人身讨论。
#. ``Reviewed-by``、``Tested-by`` 和 ``Acked-by`` 必须来自提供者本人。
#. 这些 Tag 通常针对特定版本和技术范围，实质修改后要判断是否仍有效。
#. Review Tag 不是永久附着在 Patch Subject 上，而是对具体内容的认可。
#. Maintainer 可能在应用时调整 Subject 或说明，作者应核对最终语义。
#. Patch 进入维护者树后，应确认目标分支、Commit 和任何调整。
#. 无回复时先检查收件人、公开归档、基础树、测试和 Patch 说明。
#. 合理 Ping 应保留原 Thread，并简要说明等待的 Review 或决定。
#. 不同子系统响应节奏不同，不存在统一的固定跟进间隔。
#. 高频重复发送相同 Patch 会增加噪声，不会提高技术价值。
#. Merge Window、会议、假期和大型集成工作会影响响应时间。
#. 长期无人处理时，应重新评估问题重要性、Patch 拆分和维护边界。
#. 邮件客户端、企业网关和自动免责声明可能破坏 Patch，应提前测试。
#. 作者身份、邮箱、DCO 和 Commit Author 必须与邮件材料一致。
#. Cover Letter 不应成为空泛摘要；它应减少 Reviewer 理解 Series 的成本。
#. 单个简单 Patch 通常无需形式化 Cover Letter，除非背景或子系统规则需要。
#. Review 回复属于公开工程历史，措辞应面向未来维护者。
#. 发出 Patch 只是 Review 开始，作者需要持续处理反馈、机器人结果和版本迭代。
#. 稳定投递顺序是：路径 → 维护责任 → 生成 Patch → 自测邮件 → 公开 Thread → Inline Review → 修改 Commit → 新版 Changelog。

必背路径
--------

收件人判断：

::

   修改路径与影响范围
   → MAINTAINERS 的 F:/X:/M:/R:/L:/T:
   → scripts/get_maintainer.pl 候选
   → Git History 与子系统文档复核
   → Maintainer / Reviewer / Mailing List
   → To: 与 Cc:

邮件 Series：

::

   本地逻辑 Commits
   → git format-patch --cover-letter
   → 检查 0/N 与 1/N...N/N
   → git send-email 纯文本投递
   → 公开归档
   → Inline Review
   → 修改原 Commits
   → v2/v3 + Changes

必须区分
--------

* ``MAINTAINERS`` 当前责任与 Git 历史作者：``MAINTAINERS`` 表示当前维护边界；历史作者只说明谁曾修改过代码，不自动拥有当前决策责任。
* ``get_maintainer.pl`` 候选与最终收件人：脚本输出路径和历史匹配候选；最终 To/Cc 必须按实际接口影响、子系统文档和 Review 责任筛选。
* ``git format-patch`` 生成邮件与 ``git send-email`` 投递：前者把 Commit 转换为纯文本 Patch；后者保持收件人和线程关系把 Patch 发往列表。
* Cover Letter 整体说明与单枚 Commit Message：Cover Letter 解释整个 Series 的目标、顺序和测试；每枚 Commit Message 仍必须自包含地解释自身逻辑变化。
* Inline Review 技术回应与无上下文 Top-post：Inline Reply 把答复绑定到具体评论和代码；Top-post 会切断问题与回答的对应关系。
* 新版自包含与保留旧版演进线索：v2/v3 必须独立可读；Changelog 和原线程同时保留相对上一版的变化原因。
* 邮件已经发送与邮件已经进入正确公开归档：客户端显示发送成功不证明列表收到；应以目标归档中的 Message-ID 和线程为准。

一句话结论
----------

内核邮件工作流通过路径驱动的维护者路由、纯文本 Patch Thread、可追踪版本迭代和逐项 Review 回复，把本地提交转成社区能够长期共同维护的设计记录。
