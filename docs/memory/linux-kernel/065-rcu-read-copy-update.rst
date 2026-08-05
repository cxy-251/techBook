第065章：RCU Read-Copy-Update 同步模型
=====================================

本章必须记住
------------

#. RCU 适合读多写少、读侧必须低开销、写侧可以承担复制和延迟回收成本的共享对象。
#. RCU 把三个问题拆开：新读者看见哪个版本、旧读者能否继续访问、旧对象何时真正释放。
#. 普通 RCU 读侧使用 ``rcu_read_lock()`` 和 ``rcu_read_unlock()`` 标记临界区。
#. 读侧通过 ``rcu_dereference()``、``list_for_each_entry_rcu()`` 或对应 `_rcu` API 读取受保护指针。
#. 在普通 RCU 读侧临界区内取得的对象，至少在该临界区结束前不能被 RCU 回收。
#. 离开读侧临界区后继续保存或使用对象指针，通常需要在保护范围内成功取得引用计数。
#. RCU 不保证读者看到最新版本；读者可能看到更新前或更新后的稳定对象视图。
#. 写者之间的并发不会由 RCU 自动序列化，多个更新者通常仍需要 mutex、spinlock 或其它写侧锁。
#. 发布新对象前必须完成初始化，再使用 ``rcu_assign_pointer()`` 或 `_rcu` 插入接口发布。
#. ``rcu_assign_pointer()`` 与 ``rcu_dereference()`` 配合，保证读者按 RCU 顺序看到已经初始化的对象内容。
#. 删除对象时，写者先从查找结构中摘除它，让后续新读者不再获得该对象。
#. ``list_del_rcu()``、``hlist_del_rcu()``、``rcu_replace_pointer()`` 等接口只完成可见性变化，不立即释放内存。
#. 从结构中删除旧对象后，删除前已经取得指针的读者仍可能继续访问它。
#. Grace period 表示等待开始前已经进入的 RCU 读侧临界区都已经结束。
#. ``synchronize_rcu()`` 同步等待一个 grace period，调用者在等待期间可能睡眠。
#. ``call_rcu()`` 注册异步回调，回调在 grace period 之后执行。
#. ``kfree_rcu()`` 把常见的 grace period 后释放封装成便利接口。
#. Grace period 只解决旧 RCU 读者，不自动等待普通引用、workqueue、timer、IRQ、DMA 或其它对象使用者。
#. 对象同时被 RCU 与引用计数保护时，删除路径通常需要先摘除可见指针，再等待 RCU 读者和长期引用分别结束。
#. RCU 的核心顿悟是把“新读者看不到旧对象”和“旧对象可以释放”拆成两个不同时间点。
#. Copy-update 模式通常先复制旧对象，修改副本，再原子发布新对象，最后延迟回收旧对象。
#. 复制替换让并发读者看到完整旧版本或完整新版本，避免看到原地修改的中间状态。
#. RCU 链表读侧必须使用 `_rcu` 遍历宏；写侧插入、删除和替换应使用对应 RCU 更新 API。
#. 写侧锁保护更新者之间的链表结构一致性，RCU 保护读者与回收者之间的生命周期关系。
#. 普通 RCU 读侧应保持短小；可抢占 RCU 允许被调度抢占，不等于允许任意阻塞睡眠。
#. 需要在读侧阻塞或睡眠的场景，应评估 SRCU 或目标子系统明确提供的 sleepable RCU 风味。
#. RCU 有多种风味，包括普通 RCU、SRCU、Tasks RCU 等；读写 API 和 grace period 必须来自同一协议。
#. ``rcu_read_lock_sched()`` 等历史或特定变体的语义会随内核演进，不能只按名字套用普通 RCU 规则。
#. PREEMPT_RT 会改变调度和部分读侧实现细节，但“摘除、等待旧读者、再回收”的对象模型仍然成立。
#. RCU 读侧通常不提供对象字段修改互斥；可变字段仍需锁、atomic、seqcount 或替换整个对象。
#. RCU 不能替代引用计数：它保护一个临界区内的短访问，不表达任意长时间的对象所有权。
#. RCU 不能替代内存屏障推理：必须使用 RCU 指针 API，不能用普通指针赋值和解引用绕过发布协议。
#. RCU 不能替代错误回滚：新对象构造失败时不得发布半初始化对象，旧对象仍按原状态保持可见。
#. ``call_rcu()`` 回调运行上下文具有约束，复杂或可睡眠销毁工作可能需要再转移到 workqueue。
#. RCU callback backlog 或 stall 表示 grace period、CPU quiescent state 或回调推进存在压力，需要结合配置和运行环境分析。
#. Lockdep 的 RCU 检查、KASAN、KCSAN 和 RCU stall detector 能发现部分错误使用和回收问题。
#. 阅读 RCU 代码时，必须完整找到读侧、发布点、删除点、grace period 和最终释放函数。

必背路径
--------

RCU 读取：

::

   rcu_read_lock
   → rcu_dereference 或 _rcu 遍历
   → 在临界区内读取对象
   → 需要带出指针时尝试取得普通引用
   → rcu_read_unlock
   → 只使用已复制结果或有引用保护的对象

发布新对象：

::

   分配新对象
   → 初始化所有读者可见字段
   → 写侧锁保护更新者
   → rcu_assign_pointer 或 _rcu 插入
   → 释放写侧锁
   → 新读者可以观察新对象

删除旧对象：

::

   写侧锁定位旧对象
   → list_del_rcu / hlist_del_rcu / 替换指针
   → 新读者不再获得旧对象
   → 释放写侧锁
   → synchronize_rcu 或 call_rcu
   → 等待删除前的旧读者退出
   → 等待其它长期引用和异步使用者
   → 最终释放对象

复制并替换：

::

   读取旧对象稳定状态
   → 构造并修改新副本
   → 在写侧锁下发布新版本
   → 旧读者继续使用旧版本
   → 新读者使用新版本
   → grace period 后回收旧版本

检查 RCU 完整性：

::

   找到受保护指针或链表
   → 找到所有 rcu_read_lock 范围
   → 找到 rcu_dereference 与 _rcu 遍历
   → 找到写侧锁和发布 API
   → 找到删除或替换 API
   → 找到 synchronize_rcu、call_rcu 或 kfree_rcu
   → 确认最终释放前还等待了引用和异步路径

必须区分
--------

可见性删除与内存释放
   摘除指针只阻止新读者；旧对象必须在 grace period 和其它持有者结束后释放。

RCU 与写侧锁
   RCU保护读者与回收；写侧锁序列化多个更新者和复合结构修改。

RCU 与引用计数
   RCU保证临界区内短期访问；引用计数保证对象在临界区之外长期存活。

Grace period 与所有使用者结束
   Grace period只等待对应 RCU 读者，不自动等待 timer、work、IRQ、DMA 和普通引用。

可抢占 RCU 与可睡眠读侧
   读者可被调度抢占不表示可以任意阻塞；需要睡眠应选择明确支持的 RCU 风味。

一句话结论
----------

RCU 先改变对象的可见性，再等待旧读者离开，最后回收旧对象；它把高频读取成本转移给低频更新和延迟释放路径。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 13，Concurrency, Locking, Atomics, Memory Barriers, and RCU；
* AIBook 章节：Chapter 65，RCU Read-Copy-Update as a Kernel-Scale Synchronization Model；
* 源文件：``docs/LinuxK/Part_13_Concurrency_Locking_Atomics_Memory_Barriers_and_RCU/Chapter_065_RCU_Read_Copy_Update_as_a_Kernel_Scale_Synchronization_Model.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_13_Concurrency_Locking_Atomics_Memory_Barriers_and_RCU/Chapter_065_RCU_Read_Copy_Update_as_a_Kernel_Scale_Synchronization_Model.md>`_。