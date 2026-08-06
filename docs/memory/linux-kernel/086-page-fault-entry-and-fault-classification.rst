第086章：缺页异常入口与故障分类
================================

本章必须记住
------------

#. Page fault 是 CPU/MMU 在当前指令的地址翻译或权限检查无法继续时产生的同步异常。
#. TLB miss 不等于 page fault；页表中存在合法映射时，硬件 page walk 可以补充 TLB 后继续执行。
#. Page fault 可以来自页表项不存在、写权限不足、执行权限不足、保护键、保留位错误或架构特定状态。
#. 架构入口负责取得 fault address、硬件错误码、用户态或内核态来源以及读、写、取指类型。
#. 通用内存管理把架构错误码转换成 ``FAULT_FLAG_WRITE``、``FAULT_FLAG_USER``、``FAULT_FLAG_INSTRUCTION`` 等语义。
#. 用户地址 fault 的核心对象链是：当前 task → ``mm_struct`` → 覆盖地址的 VMA → 页表项 → 匿名、文件或特殊后端。
#. VMA 表示地址范围的合法语义；页表表示当前已经实现的翻译状态，两者不能混为一层。
#. 地址落在合法 VMA 内，不代表当前已有物理页或 PTE；按需分页正是利用 fault 延迟建立这些对象。
#. 地址不在任何可接受 VMA 内，通常无法修复，应向用户进程报告 ``SIGSEGV``。
#. 地址位于 VMA 内但访问类型违反 VMA 权限，通常属于访问权限错误，而不是普通缺页。
#. ``SEGV_MAPERR`` 通常表示没有映射覆盖地址；``SEGV_ACCERR`` 通常表示映射存在但权限不允许。
#. 文件映射 VMA 合法而后端无法提供目标页时，可能产生 ``SIGBUS``，例如访问超过有效文件后端范围。
#. 栈增长是受严格边界和策略限制的特殊 VMA 扩展，不能把任意靠近栈的无效地址都视为合法。
#. 用户态合法 fault 可以通过匿名页分配、文件页装入、swap-in、COW、权限更新或特殊 ``vm_ops`` 修复。
#. 无法修复的用户 fault 转换成信号；无法通过异常表修复的内核 fault 可能形成 Oops 或 panic。
#. 内核访问用户指针时也可能触发 fault；``copy_to_user()``、``copy_from_user()`` 等路径必须依赖 uaccess 和异常表规则。
#. 原子上下文、关闭 page fault 或持有不允许睡眠的锁时，不能假设用户页 fault 可以正常完成 I/O 和内存分配。
#. ``pagefault_disable()`` 只改变当前路径允许的 fault 行为，不使无效用户指针变得安全。
#. ``handle_mm_fault()`` 是通用 fault 处理核心入口之一，具体函数拆分具有内核版本差异。
#. 通用路径会根据 VMA、页表层级和 entry 类型进入匿名页、文件页、swap、COW、大页或设备映射处理。
#. ``vm_operations_struct->fault`` 允许文件系统、驱动或特殊映射提供自己的 fault 后端。
#. 普通文件映射经常通过 ``filemap_fault()`` 把文件偏移连接到 Page Cache folio。
#. 设备 PFN、DAX、HugeTLB、shmem 和 userfaultfd 可能使用不同 fault 路径，不能机械套用普通匿名页模型。
#. Fault handler 返回 ``vm_fault_t`` 位集合，调用者必须解释 OOM、SIGBUS、SIGSEGV、MAJOR、RETRY 等结果。
#. ``VM_FAULT_RETRY`` 表示处理路径释放了部分锁或等待后要求上层重新查找和重试，不表示访问必然成功。
#. Fault 重试后 VMA、页表和对象状态可能已经变化，不能继续使用重试前未受保护的指针和判断。
#. ``VM_FAULT_OOM`` 表示 fault 处理无法取得所需内存，上层还要结合用户/内核上下文决定 OOM 或信号处理。
#. Valid/invalid 和 minor/major 是两个不同分类维度。
#. Valid/invalid 回答访问是否能由当前地址空间语义解释；minor/major 回答合法 fault 修复是否需要后端读入。
#. Minor fault 表示不需要从较慢后端把内容读入内存，仍可能涉及页分配、清零、页表建立、COW 复制和 TLB 失效。
#. Major fault 表示处理需要等待文件、swap 或其它后备存储把页内容带入内存。
#. 文件页已经在 Page Cache 中但当前进程没有 PTE，安装映射通常属于 minor fault。
#. 文件页不在内存，需要文件系统和存储读取，通常属于 major fault。
#. 匿名内存首次写入通常分配并清零新页，通常属于 minor fault。
#. 被换出的匿名页重新访问需要 swap-in，通常属于 major fault。
#. COW 写 fault 通常属于 minor fault，但复制大页或大量基础页仍可能产生明显 CPU 和内存带宽成本。
#. Major/minor 由实际 fault 结果和是否发生后端读入决定，不能只按 VMA 是文件还是匿名分类。
#. Fault 计数通常是累计结果，应使用固定时间窗口增量而不是只看启动以来总值。
#. 同一条用户指令在 fault 被成功修复后会重新执行，因此 handler 必须建立能够让重试安全完成的状态。
#. Fault 修复不仅要安装 PTE，还要处理引用计数、反向映射、LRU、memcg、NUMA、dirty/accessed 位和 TLB 一致性。
#. 页表修改后必须按架构协议使旧 TLB 翻译失效，不能只更新内存中的页表项。
#. Fault 可能在获取 mmap/VMA 锁、folio 锁、页表锁或等待 I/O 时睡眠，延迟来源必须按阶段拆分。
#. VMA 查找结构和锁实现会演进；稳定判断是 fault 期间必须持有足够保护，防止 VMA 被并发拆分、删除或改权。
#. Fault 地址来自 CPU 报告，日志中的 instruction pointer、error code 和 VMA 只是同一现场的不同层证据。
#. 用户空间崩溃排查必须同时保存 fault address、信号 ``si_code``、访问指令、maps 和相关文件后端状态。
#. 内核 fault 排查必须额外检查当前上下文、异常表、uaccess、锁状态、页表损坏和地址类型。
#. 最稳定的 fault 阅读顺序是：架构异常入口 → fault 地址与访问类型 → VMA 与权限 → 页表状态 → 后端 handler → ``vm_fault_t`` 结果。

必背路径
--------

用户态合法缺页：

::

   CPU 执行读、写或取指
   → TLB / 页表无法满足翻译或权限
   → 架构 page fault 入口
   → 提取 fault address 与访问类型
   → 找到当前 mm_struct
   → 查找覆盖地址的 VMA
   → 检查 VMA 权限和映射语义
   → handle_mm_fault
   → 分配、装入、复制或更新页表
   → 执行 TLB 一致性处理
   → 返回并重试原指令

用户态非法访问：

::

   CPU 报告 fault
   → 地址没有合法 VMA
   → 或访问类型违反 VMA 权限
   → 或映射后端无法提供页面
   → 生成 SIGSEGV / SIGBUS 信息
   → 设置 si_addr 与 si_code
   → 向当前线程递送信号
   → 默认处理通常终止并生成崩溃现场

Minor fault：

::

   地址与权限合法
   → 页面内容已经在内存或可直接构造
   → 安装已有 Page Cache 页
   → 或分配匿名零页
   → 或完成 COW 复制
   → 更新 PTE 与引用关系
   → 计入 minor fault
   → 不等待后端读入

Major fault：

::

   地址与权限合法
   → 页内容不在内存
   → 文件系统读取文件页或 swap-in
   → 当前任务等待后端 I/O
   → 页面变为可用状态
   → 安装页表映射
   → 返回 VM_FAULT_MAJOR
   → 计入 major fault

Fault 重试：

::

   handler 需要等待或释放地址空间锁
   → 返回 VM_FAULT_RETRY
   → 上层丢弃旧 VMA 与页表假设
   → 重新取得必要保护
   → 再次查找 VMA 和页表
   → 状态仍合法时继续处理
   → 状态已变化时重新分类

必须区分
--------

* TLB miss 与 Page fault：TLB miss 可由合法页表遍历解决；page fault 表示当前页表或权限条件无法让访问直接继续。
* VMA 权限与 PTE 权限：VMA 描述进程语义；PTE 描述当前硬件映射，COW 中 VMA 可写而 PTE 暂时只读。
* Valid/invalid 与 Minor/major：前者判断访问是否合法；后者只对可处理 fault 判断是否需要后端读入。
* ``SIGSEGV`` 与 ``SIGBUS``：前者常见于地址或权限错误；后者常见于映射存在但后端对象无法完成访问，具体结果由 fault 路径决定。
* 用户 fault 与内核 fault：用户 fault 通常转换为信号；内核 fault 还要检查异常表、uaccess 和当前上下文，无法修复时可能 Oops。
* Fault 返回与对象状态不变：``VM_FAULT_RETRY`` 等返回会允许锁释放和并发变化，重试必须重新验证所有对象。

一句话结论
----------

Page fault 是硬件异常事实经 VMA、页表和后端对象逐层解释后的内存构造或错误报告事件，分类时必须先判断访问是否合法，再判断修复是否需要后端 I/O。
