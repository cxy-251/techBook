第186章：理解 Linux 内核开发流程
================================

本章必须记住
------------

#. Linux 内核开发是分布式、分层维护、公开评审并由 Git 历史长期保存的工程流程。
#. 一个改动通常不会直接从个人分支进入 Mainline，而是先经过邮件列表、子系统维护者和维护者树。
#. Mainline 是最终跨子系统集成和发布主线，不是所有补丁首次评审的入口。
#. Subsystem Tree 是维护者为特定领域组织已评审改动、修复和下一周期功能的集成队列。
#. Maintainer Routing 的目标是让补丁到达拥有代码上下文、评审责任和合入路径的人与列表。
#. 文件路径是维护者路由的第一输入；补丁主题或作者猜测不能替代路径证据。
#. ``MAINTAINERS`` 把代码路径映射到维护者、Reviewer、邮件列表、状态和维护树。
#. ``M:``、``R:``、``L:``、``S:``、``F:``、``X:``、``T:`` 等字段应结合目标源码版本解释。
#. ``F:`` 表示覆盖路径，``X:`` 可排除路径；不能只看到一个宽泛条目就停止匹配。
#. ``scripts/get_maintainer.pl`` 根据补丁路径、``MAINTAINERS`` 和历史生成收件人候选。
#. ``get_maintainer.pl`` 输出是候选集合，不是自动产生的最终权责结论。
#. Git History 用于判断近期谁真实处理过同类路径和相似问题。
#. 历史作者可能只是完成过机械修改，不自动等于当前维护者。
#. 子系统文档可能规定额外的基线、前缀、邮件列表、测试、树和投递时间要求。
#. 修改公共 API、UAPI、Binding、Tracepoint 或跨子系统接口时，收件范围应覆盖所有受影响维护边界。
#. 普通公开补丁主要通过邮件列表评审；严重未公开安全问题应使用专门安全报告流程。
#. Linux 内核使用 Git 保存代码历史，却不以中心化网页 Pull Request 作为普通补丁评审主界面。
#. Patch Mail 同时承载 Commit Message、Diff、Tags、版本信息和 Review Thread。
#. Lore 等公开归档把补丁、Review、版本迭代和维护者决定保存为可搜索工程记忆。
#. 公开归档使未来维护者能够从提交追溯到原始报告、设计争论和测试证据。
#. Review Thread 属于设计过程，不只是代码发送通道。
#. Reviewer 检查 ABI、并发、错误路径、兼容性、可测试性和长期维护成本。
#. Maintainer 不只是 Reviewer；还负责路由、取舍、排队、冲突解决和向上游提交。
#. 一个补丁获得 Review 并不自动表示已经进入维护者树。
#. 进入维护者树也不自动表示一定进入当前 Mainline 周期。
#. ``linux-next`` 用于提前集成多个子系统的下一周期树，暴露跨树构建和语义冲突。
#. ``linux-next`` 出现不表示 Commit 已成为 Mainline 永久历史。
#. Mainline 开发节奏可分为子系统准备、Merge Window、``-rc`` 收敛和正式发布。
#. Merge Window 主要接收维护者已提前准备和评审的功能、重构与较大改动。
#. Merge Window 不是首次发送大型新设计的理想时间点。
#. ``-rc`` 阶段主要用于修复回归、崩溃、构建失败和严重行为错误。
#. ``-rc`` 阶段对风险容忍度更低，修复应强调问题严重性、影响范围和最小改动。
#. 正式发布后，新功能通常继续在子系统树准备下一轮；适合的修复可进入 Stable 流程。
#. Stable Tree 服务已发布内核，通常接收已经在上游存在、范围明确、风险较低的修复。
#. 同一个 Diff 在功能队列、当前 ``-rc`` 修复队列和 Stable Backport 中具有不同证据要求。
#. 功能补丁、清理补丁和修复补丁不应因为代码量相近而被视为相同风险。
#. 修复最近引入的回归时，``Fixes:``、报告链接和复现证据是重要路由材料。
#. 新功能应在 Merge Window 前完成主要 Review 和子系统集成，而不是依赖 Mainline 阶段临时讨论。
#. 子系统可能维护 ``for-next``、``for-linus``、``fixes`` 等分支，名称和精确策略具有维护者差异。
#. 分支名不是稳定 ABI；应读取目标子系统文档、树说明和维护者公告。
#. 一个补丁进入哪个树，取决于问题性质、当前周期、依赖关系、风险和维护者判断。
#. Mainline Pull Request 通常由维护者向更高层维护者或 Linus 提交，不是普通贡献者直接替代邮件评审的入口。
#. Pull Request 中的提交应已经完成子系统范围内的 Review、测试和历史整理。
#. 维护者树提供同子系统改动之间的集成缓冲，帮助发现 API 和构建组合冲突。
#. ``linux-next`` 提供跨子系统预集成，帮助发现依赖顺序和冲突。
#. CI、Build Bot 和测试农场提供自动证据，不能代替维护者对语义和生命周期的判断。
#. 机器人报告必须绑定具体 Commit、Config、Architecture、Compiler 和日志。
#. 一次机器人通过只覆盖该配置组合，不证明所有架构、子系统和硬件正确。
#. 一次机器人失败也可能来自基础设施或无关变化，必须定位到补丁和路径。
#. 补丁路由应先确认基础分支，避免基于错误树生成无法应用或重复修复的 Patch。
#. 修复应基于包含目标 Bug 且符合子系统要求的树，不能机械使用任意最新分支。
#. Series 中的依赖应明确；维护者需要知道补丁是否依赖另一个树或未合入 API。
#. 跨子系统依赖可能通过共享 Topic Branch、稳定合并点或维护者协调解决。
#. 作者不能自行假设跨树合并顺序；应在 Cover Letter 和 Review 中说明依赖。
#. 公共提交历史要求每个 Commit 可理解、可构建、可 Bisect，并拥有独立工程理由。
#. 邮件中的版本说明服务当前 Review；最终 Commit Message 服务长期 Git 历史。
#. ``---`` 之后的 Patch Commentary 通常不进入最终 Commit Log。
#. Review 结论、测试标签和问题链接应按语义保存在 Trailer 或最终说明中。
#. 上游流程不是只让代码“被接受”，还要让问题、理由、风险和责任可长期追溯。
#. 维护状态可能随人员、公司和子系统演进改变，必须以目标源码树当前 ``MAINTAINERS`` 为准。
#. 邮件列表地址、维护树 URL 和投递习惯也可能变化，不能长期复制旧教程收件人。
#. 查找旧讨论时应以 Message-ID、Subject、Commit Hash、文件路径和 Lore Thread 交叉定位。
#. 同名 Subject 可能存在多个版本；必须区分 ``v1``、``v2``、``v3`` 和最终入树 Commit。
#. 邮件中的 Patch ID 与最终 Commit Hash 不同；Rebase 或维护者调整会改变 Commit ID。
#. 最终判断补丁是否进入 Mainline，应检查目标 Mainline Git History，而不是只看邮件状态。
#. 最终判断补丁是否进入 Stable，应检查对应 Stable Branch 和发布记录。
#. 未收到回复不自动表示拒绝；可能是收件人错误、时机不佳、上下文不足或维护者负载高。
#. 合理跟进应保留线程、补充证据并遵守子系统节奏，不能频繁重复发送无变化版本。
#. 长期无响应前应重新检查收件人、Patch 质量、基线、测试和是否存在重复修复。
#. Review 中出现设计分歧时，应回到用户影响、对象模型、兼容性和维护成本，而不是把讨论简化为个人偏好。
#. 维护者可以要求拆分、重做、增加测试或拒绝接口，即使本地代码功能正常。
#. 被拒绝的本地方案可能暴露真实问题，但不具备主线可维护性。
#. 一个改动进入 Mainline 后仍可能因回归被 Revert、修复或重新设计。
#. Mainline 合入不是生命周期终点；作者仍应跟进机器人、用户和 Stable 反馈。
#. 稳定开发流程是：定位维护边界 → 选择正确基线和阶段 → 公开发送 → Review → 子系统树 → ``linux-next`` → Mainline → ``-rc`` 验证 → 发布与 Stable。

必背路径
--------

普通补丁进入主线：

::

   修改文件与影响范围
   → MAINTAINERS / get_maintainer / Git History
   → 正确维护者与邮件列表
   → Patch Mail 与公开 Review
   → Revision 与测试证据
   → Subsystem Maintainer Tree
   → linux-next 跨树集成
   → Mainline Merge Window 或 Fixes Queue
   → -rc 收敛
   → 正式发布

发布节奏：

::

   子系统树准备下一周期改动
   → Merge Window 集中合入
   → rc1 关闭大规模功能合入
   → rc2...rcN 修复回归与严重问题
   → 正式发布
   → 下一周期准备 / Stable Backport

必须区分
--------

* Mainline，与子系统维护者树；
* 邮件列表 Review，与最终 Git 合入；
* ``linux-next`` 集成，与 Mainline 永久历史；
* Merge Window 功能合入，与 ``-rc`` 阶段修复；
* Maintainer 责任，与历史作者上下文；
* ``get_maintainer.pl`` 候选输出，与最终收件人判断；
* 补丁已经发送，与补丁已经被接受。

一句话结论
----------

Linux 内核开发把一段本地改动放进维护者路由、公开邮件评审、分层 Git 树和发布节奏中，使代码、设计理由与责任历史一起进入主线。

来源
----

* 教材：AIBook《Linux Kernel》；
* Part：Part 38：Kernel Patch Workflow, Maintainers, Reviews, Regressions, and Upstream Contribution；
* 章节：Chapter 186: Understanding the Linux Kernel Development Process；
* 源文件：``docs/LinuxK/Part_38_Kernel_Patch_Workflow_Maintainers_Reviews_Regressions_and_Upstream_Contribution/Chapter_186_Understanding_the_Linux_Kernel_Development_Process.md``；
* 固定版本：``18386764582829f2b807b7b0947785eb77b50446``；
* 固定链接：https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_38_Kernel_Patch_Workflow_Maintainers_Reviews_Regressions_and_Upstream_Contribution/Chapter_186_Understanding_the_Linux_Kernel_Development_Process.md