第187章：准备 Patch、Commit Message 与 Signed-off-by
===================================================

本章必须记住
------------

#. Linux 内核补丁是 Diff 与可追踪工程论证的组合，二者缺一不可。
#. Diff 说明代码如何变化；Commit Message 说明问题为何存在、改动为何正确、影响边界是什么。
#. 一个 Patch 应表达一个可以独立评审、独立应用、独立回滚和独立 Bisect 的逻辑变更。
#. “一个逻辑变更”由问题和对象关系定义，不由文件数量或代码行数定义。
#. 一个 Patch 可以修改多个文件，只要这些修改共同完成同一个闭合变化。
#. 一个一行 Patch 也可能混入无关行为、格式整理和接口变化。
#. Bug Fix、重构、格式整理、性能优化和新功能通常应拆成不同 Patch。
#. 拆分前先写出本 Patch 要解决的单句问题。
#. 每个修改点应分类为必要修复、直接测试支撑、前置重构、顺手清理或无关格式变化。
#. 当前 Patch 只保留解决该问题必需的代码和直接证据。
#. 前置重构可以单独成 Patch，但中间状态必须可构建、可运行、可 Bisect。
#. Series 中的每个 Commit 都应拥有独立角色，不能用最后一枚“fix previous patches”清理前面错误。
#. Review 指出的修正应折回引入该逻辑的 Patch，而不是永久保留修补型尾部 Commit。
#. 提交顺序应表达依赖关系：先建立接口或不变量，再让后续 Patch 使用它。
#. 一个 Patch 的 Revert 不应留下无法构建或语义残缺的状态。
#. Commit Subject 应包含子系统前缀、局部对象和明确动作。
#. Subject 应短而具体，能够在邮件列表和 ``git log --oneline`` 中独立识别。
#. Subject 通常使用祈使语气，例如 ``net: foo: drop reference on probe error``。
#. ``fix bug``、``update code``、``misc changes`` 不说明对象、条件和动作。
#. Subject 不应只复述文件名，也不应把完整问题说明塞入一行。
#. Commit Body 第一任务是说明真实问题，而不是描述作者做了什么。
#. 问题说明应包含触发条件、错误状态和用户或系统影响。
#. 生命周期修复应说明对象在哪取得、转移、发布、释放或遗漏引用。
#. 并发修复应说明两个执行路径、保护机制、竞态窗口和失效后果。
#. ABI 修复应说明已有用户合同、发生的破坏和兼容策略。
#. 性能修改应说明工作负载、测量方法、基线、结果和副作用。
#. Commit Body 应解释根因，不能只写“avoid crash”或“fix warning”。
#. 崩溃行可能只是错误最终暴露点，说明应追溯到最初违反的不变量。
#. 修复说明应写明 Patch 改变哪条路径，以及哪些成功路径和语义保持不变。
#. 对错误路径 Patch，应说明部分初始化状态和逆序回滚关系。
#. 对锁 Patch，应说明锁保护的对象和 Context，不能只写“add lock”。
#. 对 Refcount Patch，应说明 Get/Put 的所有权主体和最后释放边界。
#. 对 RCU Patch，应说明 Publish、Read-side、Remove、Grace Period 和 Free 顺序。
#. 对硬件 Quirk，应说明受影响设备范围和为何不应影响其它设备。
#. 外部链接不能替代自包含 Commit Message。
#. ``Link:`` 或 ``Closes:`` 可保存详细报告和讨论，正文仍应保留最小充分事实。
#. Commit Message 进入永久 Git History，应面向未来维护者、Bisect、Backport 和 Revert 阅读。
#. ``---`` 之后的版本说明和测试补充主要服务当前邮件 Review，通常不进入最终 Commit Log。
#. Patch Commentary 应与永久提交说明分开，避免把 ``Changes in v2`` 写进最终历史。
#. Diffstat 帮助 Reviewer 快速判断规模，不代替实际 Diff 评审。
#. ``Signed-off-by:`` 表示签署者依据 Developer Certificate of Origin 声明有权提交该贡献。
#. ``Signed-off-by`` 不是代码质量认可，也不是 Reviewer Tag。
#. 使用 ``git commit -s`` 可添加当前提交者的 ``Signed-off-by``，仍需检查姓名和邮箱正确。
#. Sign-off 链应反映补丁实际传递路径，不能随意添加未参与或未授权的人。
#. 作者与提交者可以不同，Trailer 应准确反映 Author、Co-developed-by 和 Sign-off 关系。
#. 使用 ``Co-developed-by:`` 时，通常应紧邻对应共同开发者的 ``Signed-off-by:``。
#. ``Fixes:`` 指向引入问题的 Commit，通常采用不少于 12 位 Hash 和原 Subject。
#. ``Fixes:`` 不是“相关 Commit”，而是帮助定位引入缺陷的责任边界。
#. 添加 ``Fixes:`` 前应通过源码历史、行为变化或 Bisect 证明引入关系。
#. 错误的 ``Fixes:`` 会误导 Stable、回归跟踪和历史分析。
#. ``Reported-by:`` 记录最初报告问题的人，需使用对方公开身份并尊重许可。
#. ``Tested-by:`` 表示某人对特定版本和范围执行了测试并确认结果。
#. 作者不能自行替别人添加 ``Tested-by``、``Reviewed-by`` 或 ``Acked-by``。
#. ``Reviewed-by:`` 表示 Reviewer 对该版本技术内容完成了评审并认可。
#. ``Acked-by:`` 通常表示对方向或范围的认可，技术评审强度可能与 ``Reviewed-by`` 不同。
#. Patch 发生实质算法、ABI、锁或错误路径变化后，旧 Review Tag 可能不再适用。
#. 只改拼写或 Commit Message 时，Tag 是否保留仍应按 Reviewer 认可范围和社区习惯判断。
#. ``Link:`` 用于关联相关讨论、报告、文档或历史邮件。
#. ``Closes:`` 用于表达该 Patch 解决所链接的公开问题，链接应可长期访问。
#. ``Closes:`` 不应指向与实际修复范围不一致的宽泛报告。
#. 安全问题在公开前可能不能使用公开 ``Closes:``，应遵守安全流程。
#. ``Cc: stable@vger.kernel.org`` 属于 Stable 候选提示，不代表 Patch 一定被 Backport。
#. Stable 相关 Trailer 应在 Patch 已符合上游和 Stable 规则时使用。
#. Tag 顺序应保持清晰，通常先问题和来源类 Trailer，再 Review/Test，再 Sign-off 链。
#. 精确 Trailer 规则和顺序可能随文档演进，应读取目标源码树 ``Documentation/process/``。
#. ``scripts/checkpatch.pl`` 能发现格式、常见风格和部分 Commit Message 问题。
#. Checkpatch 是辅助工具，不证明生命周期、锁、ABI 和算法正确。
#. Checkpatch Warning 需要人工判断，既不能全部忽略，也不能无条件机械修改。
#. 为消除 Checkpatch Warning 而改变正确语义可能制造新 Bug。
#. Patch 生成前应清理本地 Diff，确认没有调试日志、临时开关、生成文件或无关格式变化。
#. 应使用 ``git diff --check`` 检查空白错误，并检查实际 Commit 范围。
#. 应阅读 ``git show --stat --oneline`` 和完整 ``git show``，以 Reviewer 视角复查。
#. Patch 应基于正确树和基线，避免重复提交已经存在的修复。
#. 重发前应比较旧版与新版，确认只发生预期变化。
#. Cover Letter 中的测试矩阵不能替代每枚 Patch 对自身逻辑的说明。
#. Series 的整体设计放在 Cover Letter；单枚 Commit Message 必须在脱离 Cover Letter 后仍可理解。
#. Patch 的永久历史不能依赖 Reviewer 记住邮件上下文。
#. 一个高质量 Commit Message 应让未来维护者回答：出了什么问题、为什么、怎样修、影响谁、如何验证。
#. “代码很明显”不能代替问题说明，尤其在错误路径、并发和硬件条件中。
#. 小 Patch 也需要说明，因为稳定回灌和回归分析往往正依赖这些一行修复。
#. 大 Patch 应避免在 Commit Message 中逐行复述 Diff，应说明高层不变量和关键取舍。
#. 如果无法用一段清晰文字解释 Patch，通常说明问题边界或 Series 拆分仍不清楚。
#. 补丁准备的稳定顺序是：单句问题 → 清理 Diff → 拆分逻辑 Commit → 写 Subject/Body → 添加真实 Trailer → 检查 Patch → 生成邮件材料。

必背路径
--------

逻辑 Patch：

::

   本地 Diff
   → 写出单句问题
   → 标记每个修改点的角色
   → 移除无关清理与格式变化
   → 确认单独构建、应用、回滚和 Bisect
   → 形成一个逻辑 Commit

Commit Message：

::

   Subject：子系统 + 对象 + 动作
   → 问题与触发条件
   → 根因和错误状态
   → 修复方式与保持不变的路径
   → 影响范围与测试
   → Fixes / Reported-by / Link / Closes
   → Reviewed-by / Tested-by / Acked-by
   → Signed-off-by

必须区分
--------

* 一个逻辑变更，与一个文件；
* Diff，与工程论证；
* Subject，与完整问题说明；
* ``Signed-off-by`` DCO 声明，与 ``Reviewed-by`` 技术认可；
* ``Fixes:`` 引入问题的 Commit，与普通相关历史；
* 永久 Commit Message，与 ``---`` 后的版本 Commentary；
* Checkpatch 通过，与补丁技术正确。

一句话结论
----------

可上游评审的内核 Patch 必须把一个逻辑代码变化、一个自包含问题论证和一条真实责任与证据 Trailer 链整理成同一个可长期追溯的提交。

来源
----

* 教材：AIBook《Linux Kernel》；
* Part：Part 38：Kernel Patch Workflow, Maintainers, Reviews, Regressions, and Upstream Contribution；
* 章节：Chapter 187: Preparing Patches, Commit Messages, and Signed-off-by；
* 源文件：``docs/LinuxK/Part_38_Kernel_Patch_Workflow_Maintainers_Reviews_Regressions_and_Upstream_Contribution/Chapter_187_Preparing_Patches_Commit_Messages_and_Signed_off_by.md``；
* 固定版本：``18386764582829f2b807b7b0947785eb77b50446``；
* 固定链接：https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_38_Kernel_Patch_Workflow_Maintainers_Reviews_Regressions_and_Upstream_Contribution/Chapter_187_Preparing_Patches_Commit_Messages_and_Signed_off_by.md