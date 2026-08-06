第189章：处理 Review 反馈、版本迭代与回归
=========================================

核心知识点
----------

Review 评论指向系统合同
   表面上的一句评论，通常在检查 ABI、并发、错误路径、兼容性、测试或维护成本。作者应先把它映射到具体对象、状态、入口和用户影响。

修正应折回原逻辑 Commit
   代码、说明、拆分和测试的修改应进入引入该逻辑的 Patch，保持每个 Commit 的最终历史完整，而不是追加 ``fix review comments`` 尾部补丁。

新版必须同时自包含和可追踪
   v2、v3 应独立描述完整方案；Cover Letter 或 ``---`` 后的 Changelog 负责列出相对上一版的具体变化，Commit Message 则保存最终因果链。

Review Tag 绑定特定版本
   拼写或说明调整通常不会改变认可范围；算法、ABI、锁、生命周期和错误路径发生实质变化后，应重新取得相应 Review 或测试确认。

Regression 是已有行为的破坏
   启动失败、设备消失、性能退化、功耗上升和旧用户程序失效都可能构成回归。它通常比长期存在的普通 Bug 具有更高恢复优先级。

回归调查必须固定比较条件
   Good 与 Bad Kernel 应使用尽可能一致的 Config、硬件、用户空间和负载。复现不稳定或环境漂移会污染 ``git bisect`` 的结论。

Bisect 只定位首次坏提交
   Culprit Commit 是最早观察到坏行为的位置，不自动等于完整根因。仍需结合 Diff、对象生命周期、调用路径和并发关系解释为何破坏合同。

修复、Revert 与跟踪形成闭环
   能快速证明安全时可提交最小修复；当前 ``-rc`` 阶段风险过高时可先 Revert 恢复基线。最终还要确认修复进入目标 Mainline 或 Stable Branch，并由原环境验证。

关键路径
--------

Review 迭代：

::

   v1 Review 评论
   → 映射到对象与合同
   → 修改原 Commit
   → 同步 Commit Message 和测试
   → 生成 v2 / v3
   → Changelog 与逐项回复

回归处理：

::

   固定 Good / Bad 与环境
   → 稳定 Reproducer
   → git bisect
   → 验证 Culprit 和根因
   → 最小修复或 Revert
   → 报告者验证
   → Mainline / Stable 跟踪

概念辨析
--------

* **评论措辞与设计压力**：评论可能很短；真正需要回应的是 ABI、并发、错误路径或维护成本。
* **Changelog 与 Commit Message**：Changelog 记录版本间变化；Commit Message 保存最终问题与修复论证。
* **Bisect Culprit 与完整根因**：Bisect 找到首次坏提交；根因还需解释对象或用户合同如何被破坏。
* **普通 Bug 与 Regression**：普通 Bug 可能长期存在；Regression 破坏此前可工作的行为。
* **Revert 与放弃功能**：Revert 先恢复稳定基线，功能仍可在重新设计后再次提交。
* **Tracker 状态与实际入树**：跟踪工具只记录流程；目标 Git Branch 中出现修复 Commit 才表示真正完成。

本章结论
--------

Review 迭代用于把社区质疑转化为更清晰的 Commit 历史，回归处理则通过稳定复现、Bisect、修复或 Revert 和目标分支验证，恢复已经存在的用户合同。