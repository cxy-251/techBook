第086章：缺页异常入口与故障分类
================================

核心知识点
----------

Page fault 是同步异常
   CPU 在执行当前读、写或取指操作时，发现页表翻译或权限无法继续，立即进入架构异常入口。处理完成后，原指令可能被重试，也可能转为信号或内核异常。

TLB miss 不等于 Page fault
   TLB 未命中时，硬件仍可遍历合法页表并补充缓存。只有页表缺失、权限受限或架构状态无法满足访问时，才需要进入缺页处理。

架构入口提供故障事实
   架构代码取得 fault address、硬件错误码、用户态或内核态来源，以及读、写、取指类型，再转换为 ``FAULT_FLAG_WRITE``、``FAULT_FLAG_USER``、``FAULT_FLAG_INSTRUCTION`` 等通用语义。

VMA 先解释地址是否合法
   ``mm_struct`` 描述当前地址空间，VMA 描述一段地址范围的权限和后端语义。VMA 存在而 PTE 缺失可以是正常 demand paging；地址无 VMA 或权限不匹配通常无法修复。

页表表示当前实现状态
   VMA 说明地址应当怎样工作，页表说明当前是否已经有映射及硬件权限。COW 中 VMA 可以允许写，而 PTE 暂时只读，用于捕获首次写入。

通用处理由后端语义分流
   ``handle_mm_fault()`` 一类入口根据 VMA、页表项和后端状态进入匿名页、文件页、swap、COW、大页或特殊 ``vm_ops->fault`` 路径。

``vm_fault_t`` 是结果协议
   Fault handler 通过 ``VM_FAULT_MAJOR``、``VM_FAULT_RETRY``、``VM_FAULT_OOM``、``VM_FAULT_SIGBUS`` 等结果位告诉上层本次处理发生了什么。返回重试时，旧 VMA 和页表判断必须全部重新验证。

合法性与成本是两条分类轴
   Valid/invalid 判断访问是否符合地址空间语义；minor/major 判断合法 fault 的修复是否需要从文件、swap 或其它后端读入内容。

Minor fault 仍可能昂贵
   Minor fault 不需要后端读入，但可能包含匿名页分配、清零、COW 复制、大页拆分、页表更新、反向映射和 TLB shootdown。

Major fault 体现后端读入
   文件页不在 Page Cache、匿名页需要 swap-in，或其它后端必须提供内容时，任务通常需要等待 I/O，处理结果计为 major fault。

用户 Fault 与内核 Fault 处理边界不同
   无法修复的用户访问通常转为 ``SIGSEGV`` 或 ``SIGBUS``；内核访问还要检查 uaccess、异常表和当前上下文，无法修复时可能形成 Oops 或 panic。

Fault 修复必须闭合完整状态
   成功处理不只是安装 PTE，还要维护页面引用、rmap、LRU、memcg、dirty/accessed 位和 TLB 一致性，确保原指令重试时看到合法状态。

关键路径
--------

用户态合法缺页：

::

   CPU 访问虚拟地址
   → 架构异常入口取得地址和访问类型
   → 找到当前 task 的 mm_struct
   → 查找覆盖地址的 VMA
   → 验证范围与读写执行权限
   → handle_mm_fault
   → 分配、装入、复制或修改页表
   → 维护引用、rmap 和 TLB
   → 返回并重试原指令

用户态非法访问：

::

   CPU 报告 fault
   → 地址没有可接受 VMA
   → 或访问类型违反 VMA 权限
   → 或映射后端无法提供页面
   → 构造 si_addr 与 si_code
   → 递送 SIGSEGV 或 SIGBUS

Fault 重试：

::

   Handler 需要等待或释放地址空间锁
   → 返回 VM_FAULT_RETRY
   → 丢弃旧 VMA、PTE 和对象假设
   → 重新取得必要保护
   → 重新查找并分类 fault
   → 状态仍合法时继续处理

概念辨析
--------

* TLB miss 与 Page fault：前者是翻译缓存未命中；后者是当前页表或权限无法直接完成访问。
* VMA 与 PTE：VMA 保存范围级语义；PTE 保存当前页级硬件映射和权限。
* Valid/invalid 与 Minor/major：前者判断能否修复；后者判断合法修复是否需要后端读入。
* ``SIGSEGV`` 与 ``SIGBUS``：前者常见于地址或权限错误；后者常见于映射存在但后端对象无法完成访问。
* 用户 Fault 与内核 Fault：用户路径通常转换为信号；内核路径还依赖异常表、uaccess 和执行上下文。
* ``VM_FAULT_RETRY`` 与继续旧判断：重试允许并发状态变化，所有未受保护的旧对象和结论都已失效。

本章结论
--------

Page fault 是硬件异常事实经 VMA、页表和后端对象逐层解释后的内存构造或错误报告事件。分类时先判断访问是否合法，再判断修复是否需要后端 I/O。
