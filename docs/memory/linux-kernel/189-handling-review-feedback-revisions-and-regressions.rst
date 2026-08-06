第189章：处理 Review 反馈、版本迭代与回归
=========================================

本章必须记住
------------

#. Patch 进入 Review 后，本地 Diff 变成一条公开、可追踪的工程记录。
#. Review 评论通常不是孤立风格偏好，而是在对设计施加 ABI、并发、错误路径、兼容性和维护压力。
#. 作者首先应把评论映射到具体对象、状态、入口和用户合同。
#. 评论指向 ABI 时，要检查已有用户程序、脚本、结构布局、错误码和语义是否改变。
#. 评论指向并发时，要检查锁、引用、状态位、异步回调和 Teardown 之间的窗口。
#. 评论指向错误路径时，要检查部分初始化、资源拥有者和逆序回滚。
#. 评论指向兼容性时，要检查旧硬件、Firmware、配置和 Workload 是否仍按原合同工作。
#. 评论指向测试时，要说明测试对象、配置、触发条件、命令范围和结果含义。
#. 评论指向维护成本时，要检查新抽象、分支、参数和特殊路径是否必要。
#. 作者应判断反馈需要代码修改、Commit Message 修改、Patch 拆分、测试补充还是技术解释。
#. 不能把所有 Review 意见都塞入一枚新的“fix review comments”尾部 Patch。
#. 修改应折回引入该逻辑的原 Patch，保持每个 Commit 的最终历史完整。
#. Review 后的 Series 仍应保证每个中间 Commit 可构建、可运行和可 Bisect。
#. 新版 Patch Series 必须自包含，不能依赖 Reviewer 记住旧版全部讨论。
#. 新版同时要保留演进线索，使参与旧版的人能检查意见是否闭合。
#. Cover Letter 或 ``---`` 后 Changelog 用于说明 v1 到 v2、v3 的变化。
#. Changelog 应按 Patch 和问题具体列出修改，而不是只写“address comments”。
#. 每枚 Patch 的 Commit Message 也应随设计变化同步更新。
#. 新版只改 Diff、不改已过时的 Commit Message，会让最终历史错误描述代码。
#. Commit Message 自包含服务未来 Git 历史；Changelog 服务当前邮件 Review。
#. Series 拆分发生变化时，应在 Cover Letter 说明为何重排、合并或新增 Patch。
#. 新版可以改变 Patch 数量，只要逻辑边界更清楚且历史可理解。
#. 不应为了保持编号稳定而保留错误拆分。
#. Reviewer 标签表达对特定版本和范围的认可。
#. v2 仅修改拼写、注释或说明时，旧 Tag 可能仍适用。
#. v2 修改算法、ABI、锁、生命周期或错误路径时，旧 Tag 通常需要重新确认。
#. 作者不能自行判断“改动很小”而机械保留所有 Review Tag。
#. ``Tested-by`` 也绑定测试版本和条件，实质改变行为后应让测试者重新验证。
#. Review 回复应逐项说明变更和理由，不能把新版 Patch 当作唯一答复。
#. 保留 Thread 上下文能帮助后来维护者理解设计为何演进。
#. 如果保留原方案，应直接说明不修改的技术理由和证据。
#. Review 分歧应围绕对象、用户影响和维护成本收敛，而不是围绕权威或作者意图。
#. Author Intent 不等于代码实际语义，最终判断必须基于路径和状态。
#. Reviewer 也可能误解；这种情况应先检查 Patch 是否自描述，再提供反例或源码证据。
#. Review 完成不表示 Patch 永远正确，进入树后仍可能暴露回归。
#. Regression 是以前可工作的用户可见行为在新内核中失效。
#. 回归可以表现为启动失败、设备消失、性能退化、功耗上升、用户程序异常或硬件不兼容。
#. 回归处理优先级通常高于普通新 Bug，因为它破坏了已有可工作基线。
#. “No regressions” 不表示绝不允许任何行为变化，而是已有用户合同不能无正当迁移被破坏。
#. 回归报告必须先固定 Good Version、Bad Version、硬件、配置、触发步骤和错误证据。
#. “最新内核坏了”不能直接定位到具体 Commit 或子系统。
#. Good/Bad 判断应使用相同配置、硬件、用户空间和尽可能一致的负载。
#. 版本之间配置漂移会让 ``git bisect`` 得出错误 Culprit。
#. ``git bisect`` 在已知 Good 与 Bad Commit 之间选择中点，依赖测试将每个中点分类。
#. Bisect 的测试函数必须可靠、可重复并能区分真正 Good、Bad 和无法测试。
#. 编译失败、无关硬件问题或测试环境失效应标为 Skip，而不是随意判定 Bad。
#. Flaky Reproducer 会污染 Bisect；应先提高重复率或定义统计判定。
#. 每个中间 Commit 可构建、可运行，是补丁拆分和主线可 Bisect 的重要要求。
#. Culprit Commit 是最早观察到行为破坏的 Commit，不自动等于最终根因位置。
#. Culprit 可能暴露更早潜伏的 Bug，也可能与另一个并行变化交互。
#. Bisect 结果应结合 Diff、对象状态、调用路径和报告一起解释。
#. 修复回归通常有三种方向：最小修复、完整修复或先 Revert 再重新设计。
#. 在当前 ``-rc`` 收敛阶段，如果无法快速证明修复安全，Revert 可能比带风险的新设计更合适。
#. Revert 不是承认需求无效，而是优先恢复已有用户行为和可测试基线。
#. Revert 本身也要测试，尤其当原 Commit 后已有依赖改动。
#. 修复 Patch 应带 ``Fixes:`` 指向引入回归的 Commit。
#. ``Fixes:`` 应基于 Bisect、历史或明确路径证据，不能只指向最近相关提交。
#. ``Closes:`` 可关联公开回归报告，表示 Patch 解决该报告中的问题。
#. ``Link:`` 可关联讨论、测试日志、历史报告或设计背景，不一定表示关闭问题。
#. Trailer 中的链接应指向稳定公开记录并与 Commit Message 中的事实一致。
#. ``Reported-by:`` 记录报告者贡献；``Tested-by:`` 可记录报告者验证修复的结果。
#. 回归报告者的硬件和环境通常是修复验证的重要测试点。
#. regzbot 等回归跟踪工具通过邮件指令和公开线程关联报告、Culprit 与修复。
#. regzbot 精确命令和语法可能演进，应读取目标时期的回归处理文档。
#. 跟踪工具记录状态，不替代技术修复和 Maintainer 决策。
#. 回归线程应明确：何时开始、哪个版本正常、哪个版本异常、影响谁、当前状态是什么。
#. 修复进入 Maintainer Tree 后仍要继续跟踪 Mainline 和 Stable 状态。
#. Patch 在子系统树测试通过，不等于所有用户回归已经结束。
#. 最终需要确认修复进入包含回归的目标 Mainline 或 Stable Branch。
#. 用户验证应基于包含修复的具体 Commit 或构建，不应只说“试试最新版本”。
#. 修复后原报告症状消失仍不够，还要检查正常路径和邻接硬件没有新回归。
#. 回归修复的测试应覆盖触发路径、未触发路径和错误路径。
#. 性能回归需要固定负载、测量分布、机器拓扑和噪声范围。
#. 性能变化不能只用单次平均值作为 Good/Bad 判据。
#. ABI 回归修复应使用真实旧用户程序或对应 Selftest 验证。
#. 驱动回归应同时验证 Probe、运行、Suspend/Resume、Remove 和重新绑定，范围按问题决定。
#. 回归进入 Stable 后还要考虑不同版本 API、上下文和 Backport 冲突。
#. Mainline 修复不能机械 Cherry-pick 到旧版，必须验证依赖和语义。
#. 作者发出 v2/v3 后仍应跟踪 Build Bot、测试者和 Maintainer 的新反馈。
#. 一次 Review 中没有发现问题，不表示其它架构和配置不会失败。
#. 自动测试失败应保存原始日志、Commit、Config 和触发命令，避免只转述“CI 红了”。
#. 如果失败与当前 Patch 无关，应说明证据并避免把真实基础设施问题永久忽略。
#. Revision 的稳定顺序是：评论分类 → 对象/合同分析 → 修改原 Commit → 同步说明和测试 → 生成新版 → 保留 Changelog → 逐项回复。
#. Regression 的稳定顺序是：报告 → 固定 Good/Bad → 稳定复现 → Bisect → 验证 Culprit → 修复或 Revert → 关联报告 → 用户验证 → 跟踪入树。

必背路径
--------

Review Revision：

::

   PATCH v1
   → Review 评论
   → 映射到 ABI / 并发 / 错误路径 / 兼容性 / 测试
   → 修改原逻辑 Commit
   → 更新 Commit Message 与测试证据
   → 生成 PATCH v2
   → Changes in v2
   → 逐项回复旧 Thread

Regression：

::

   用户报告已有行为失效
   → 固定 Good / Bad Kernel 与环境
   → 稳定 Reproducer
   → git bisect
   → 验证 Culprit Commit 和对象路径
   → 最小修复或 Revert
   → Fixes / Closes / Link / Reported-by
   → 报告者和相关测试验证
   → Maintainer Tree / Mainline / Stable 跟踪

必须区分
--------

* Review 评论的表面措辞，与背后的设计压力；
* 新版自包含，与丢失版本演进历史；
* Changelog，与最终 Commit Message；
* Bisect Culprit，与经过验证的完整根因；
* 普通 Bug，与破坏已有工作行为的 Regression；
* Revert 恢复基线，与永久放弃功能；
* ``Closes:`` 关闭报告，与 ``Link:`` 提供相关记录；
* 跟踪工具状态，与修复真正进入目标树。

一句话结论
----------

Review 迭代把社区质疑转成更完整的设计历史，而回归处理把已有用户承诺、Culprit Commit、修复和验证记录连接成可公开追踪的闭环。

来源
----

* 教材：AIBook《Linux Kernel》；
* Part：Part 38：Kernel Patch Workflow, Maintainers, Reviews, Regressions, and Upstream Contribution；
* 章节：Chapter 189: Handling Review Feedback, Revisions, and Regressions；
* 源文件：``docs/LinuxK/Part_38_Kernel_Patch_Workflow_Maintainers_Reviews_Regressions_and_Upstream_Contribution/Chapter_189_Handling_Review_Feedback_Revisions_and_Regressions.md``；
* 固定版本：``18386764582829f2b807b7b0947785eb77b50446``；
* 固定链接：https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_38_Kernel_Patch_Workflow_Maintainers_Reviews_Regressions_and_Upstream_Contribution/Chapter_189_Handling_Review_Feedback_Revisions_and_Regressions.md