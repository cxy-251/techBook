第186章：理解 Linux 内核开发流程
================================

核心知识点
----------

内核开发采用分层维护
   普通补丁通常先进入对应子系统，由维护者和邮件列表完成评审，再进入维护者树、``linux-next`` 和 Mainline。贡献者通常不会直接把补丁送入最终主线。

代码路径决定维护边界
   ``MAINTAINERS`` 用 ``F:``、``X:``、``M:``、``R:``、``L:`` 和 ``T:`` 等字段，把源码路径映射到维护者、Reviewer、邮件列表和维护树。应以目标源码树中的当前文件为准。

维护者脚本只提供候选
   ``scripts/get_maintainer.pl`` 根据补丁路径、维护规则和历史生成收件人候选，最终路由仍需结合公共接口影响、子系统文档和跨树依赖人工判断。

公开邮件承担评审与归档
   Patch Mail 同时承载 Commit Message、Diff、Trailer、版本信息和 Review Thread。公开归档使未来维护者能够追溯问题、设计取舍和测试证据。

Git 树表示不同集成阶段
   子系统树保存已评审的领域改动，``linux-next`` 进行跨子系统预集成，Mainline 形成最终发布历史。进入前一阶段不自动保证进入后一阶段。

发布周期约束改动类型
   Merge Window 主要合入已提前准备的功能和重构；``-rc`` 阶段主要处理回归、崩溃和高优先级修复；Stable Tree 面向已发布内核接收范围明确的上游修复。

自动测试是证据而非裁决
   Build Bot、CI 和测试农场能够暴露特定 Config、Architecture 和 Compiler 下的问题，仍不能替代维护者对 ABI、并发、生命周期和维护成本的判断。

最终状态以目标 Git 历史为准
   邮件已发送、获得 Review 或进入 ``linux-next`` 都不等于已经合入。是否进入 Mainline 或 Stable，应检查对应分支中的实际 Commit。

关键路径
--------

普通补丁进入主线：

::

   修改路径与影响范围
   → MAINTAINERS / get_maintainer / Git History
   → Maintainer、Reviewer 与 Mailing List
   → Patch Mail 与公开 Review
   → Revision 和测试证据
   → Subsystem Tree
   → linux-next
   → Mainline

发布节奏：

::

   子系统提前准备
   → Merge Window 合入功能
   → -rc 阶段收敛回归
   → 正式发布
   → 适用修复进入 Stable 评估

概念辨析
--------

* **子系统树与 Mainline**：子系统树是领域维护者的集成队列；Mainline 是跨子系统最终发布主线。
* **公开 Review 与实际合入**：Review 形成技术结论；提交出现在目标 Git Tree 中才表示真正合入。
* **``linux-next`` 与永久历史**：``linux-next`` 用于预集成测试，其中的提交仍可能修改、撤回或延后。
* **Merge Window 与 ``-rc``**：前者主要接收已准备好的功能；后者主要接收低风险修复。
* **维护者与历史作者**：维护者承担当前路由和合入责任；历史作者只提供实现背景。
* **Mainline 修复与 Stable 修复**：Mainline 面向当前上游代码；Stable 只评估已上游、风险可控的修复。

本章结论
--------

Linux 内核开发通过路径驱动的维护者路由、公开邮件评审、分层 Git 树和发布周期，把本地改动转化为可追踪、可集成、可长期维护的主线历史。