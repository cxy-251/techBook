第070章：页表调试与地址转换证据
================================

本章必须记住
------------

#. 虚拟内存问题应拆成四层：地址值、VMA 范围策略、页表项状态、物理页或 swap 后端。
#. ``/proc/<pid>/maps`` 先回答地址是否落入某个 VMA，以及该范围的权限、文件偏移和后端来源。
#. ``/proc/<pid>/smaps`` 在 VMA 基础上补充 Size、RSS、PSS、匿名页、共享页、脏页和 swap 等统计。
#. ``maps`` 中存在一行映射只证明 VMA 存在，不证明其中每个虚拟页已经分配物理页。
#. ``Size`` 表示虚拟范围大小，``Rss`` 表示当前驻留页面量，二者差距可以来自 lazy allocation、回收或尚未访问。
#. ``Pss`` 把共享页按共享者数量分摊，更适合估算一个进程对共享内存的比例贡献。
#. ``Private_Dirty`` 常表示当前进程私有且已修改的驻留页面，COW 后匿名页经常体现在此类统计中。
#. ``/proc/<pid>/pagemap`` 为每个虚拟页提供一条 64 位页级记录。
#. 读取 pagemap 时，文件偏移按 ``(virtual_address / page_size) * 8`` 计算。
#. Pagemap 可以表示页面是否 present、是否 swapped、soft-dirty、exclusive 和文件/共享匿名等状态。
#. Pagemap 位含义具有版本差异，工具必须以目标内核文档和源码为准。
#. Present 表示当前有可用页表映射；swapped 表示内容由 swap 条目承载，访问时可能需要换入。
#. Present 为 false 且 swapped 为 false，可能表示尚未分配、文件洞、特殊映射、VMA 外地址或映射已撤销。
#. Pagemap 中的 PFN 可见性受权限限制；现代内核通常要求 ``CAP_SYS_ADMIN``，普通用户看到的 PFN 可能被清零。
#. PFN 为 0 不能单独证明页面未映射，还要结合 present、权限、内核版本和零页等情况判断。
#. 在权限允许时，PFN 可以继续关联 ``/proc/kpageflags`` 和 ``/proc/kpagecount`` 观察物理页标志与映射计数。
#. Huge page、THP 和复合页会改变 PFN、page count 和统计解释，不能按普通 4 KiB 页机械推断。
#. Page fault 是 CPU 地址翻译或权限检查不能直接完成访问时进入内核的异常。
#. Minor fault 表示缺页处理不需要从慢速存储读取目标页，例如匿名分配、COW 或 page cache 命中。
#. Major fault 表示处理过程需要 I/O，例如文件页读入或 swap 换入。
#. Minor 和 major fault 都可以是正常运行路径，只有频率、延迟和业务语境异常时才构成性能问题。
#. 一个地址发生 fault 时，应先确认是否落入 VMA，再确认访问类型是否符合权限，最后检查 present、swap 和后端状态。
#. VMA 存在且权限允许、PTE 不 present 时，缺页通常可以尝试建立映射。
#. 地址不在任何 VMA 中通常形成映射缺失类错误。
#. 地址在 VMA 中但访问类型违反权限时，通常形成权限类错误。
#. 用户态 ``SIGSEGV`` 的 ``siginfo_t.si_addr`` 保存故障地址，是定位 VMA 的第一证据。
#. ``SEGV_MAPERR`` 通常表示地址没有对应映射，``SEGV_ACCERR`` 通常表示映射存在但访问权限不允许。
#. 具体信号码和架构错误码要按目标系统解释，不能只看信号名称。
#. Page fault 错误码通常包含读/写、用户/内核、present/权限和执行等架构信息。
#. 内核态 fault 还可能通过 exception table 修复用户访问或探测路径，不能一律解释为内核崩溃。
#. 用户态非法访问可能转为 SIGSEGV 或 SIGBUS；文件截断、设备映射和特殊后端可能产生不同信号语义。
#. ``/proc/<pid>/stat``、``getrusage``、``perf stat`` 等可以提供 fault 计数，但计数本身不包含具体地址。
#. Ftrace、perf fault 事件和 eBPF 可用于记录 fault 时间线，但采集能力依赖内核配置与权限。
#. 调试内存增长时，应先比较 VMA ``Size``、``Rss``、``Pss`` 和匿名/文件分类，再判断虚拟预留、真实驻留或共享分摊。
#. 调试频繁 major fault 时，应检查文件 I/O、page cache、swap、内存压力和访问局部性。
#. 调试频繁 minor fault 时，应检查首次触页、COW、匿名分配、THP 和映射抖动。
#. 读取 ``maps``、``smaps`` 和 ``pagemap`` 都是瞬时观察；目标进程可能同时修改 VMA 和页表。
#. 分析必须记录 PID、线程、地址、访问类型、时间、页大小、架构、内核版本和权限环境。
#. 对另一个进程读取内存映射证据会受 ptrace、Yama、namespace、hidepid 和 capability 等权限控制。
#. 调试结果不能只依赖一个接口；应把 VMA、页表、fault、信号、日志和源码处理路径互相验证。
#. 最终结论要明确问题发生在范围缺失、权限错误、页面未驻留、I/O 换入、COW、页表陈旧还是对象生命周期。

必背路径
--------

分析一个故障地址：

::

   记录 PID、故障地址和访问类型
   → 在 /proc/<pid>/maps 找覆盖范围
   → 没有 VMA 时判断映射缺失
   → 有 VMA 时检查 r/w/x 权限
   → 读取 smaps 判断映射驻留与后端分类
   → 必要时读取 pagemap 的 present / swapped 状态
   → 对照 fault 类型和 siginfo
   → 回到缺页或权限处理源码

读取 pagemap：

::

   获取系统 page size
   → 虚拟地址除以 page size 得到虚拟页号
   → 乘 8 得到 pagemap 文件偏移
   → 读取 8 字节记录
   → 解析 present、swapped 和版本相关标志
   → 检查当前权限是否允许查看 PFN
   → 需要时再关联 kpageflags / kpagecount

区分 minor 与 major fault：

::

   CPU 触发 page fault
   → 查找 VMA 与权限
   → 页面已在 page cache 或只需匿名分配 / COW
   → 无存储 I/O则记录 minor fault
   → 需要从文件或 swap 读取
   → 完成 I/O 后建立映射
   → 记录 major fault

分析 SIGSEGV：

::

   保存 si_addr 和 si_code
   → maps 查地址是否有映射
   → 无映射时检查悬空指针、越界和已 munmap
   → 有映射时检查访问权限与执行属性
   → 检查页表和对象生命周期
   → 对照反汇编确定故障指令和访问类型
   → 复核并发 unmap / mprotect / free 路径

必须区分
--------

VMA 存在与页面 present
   VMA 定义范围；present 表示某个具体虚拟页当前有可用页表映射。

虚拟大小与驻留大小
   Size 是地址范围；RSS 是当前驻留页，PSS 是共享页按比例分摊。

Minor fault 与 major fault
   Minor 不需要慢速存储 I/O；major 需要文件或 swap I/O。

``SEGV_MAPERR`` 与 ``SEGV_ACCERR``
   前者通常是映射缺失；后者通常是映射存在但权限不允许。

PFN 为 0 与页面不存在
   PFN 可能因权限被屏蔽，必须结合 present 和权限环境解释。

瞬时证据与稳定状态
   Procfs 输出可能在读取时变化，复杂结论需要多次采样和 trace 时间线。

一句话结论
----------

页表调试必须按“地址 → VMA → 页表项 → 页面后端 → fault 结果”逐层取证，任何单个地址、RSS、PFN 或 SIGSEGV 都不足以独立解释根因。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 14，Virtual Memory, Address Spaces, and Page Tables；
* AIBook 章节：Chapter 70，Page Table Debugging and Address Translation Evidence；
* 源文件：``docs/LinuxK/Part_14_Virtual_Memory_Address_Spaces_and_Page_Tables/Chapter_070_Page_Table_Debugging_and_Address_Translation_Evidence.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_14_Virtual_Memory_Address_Spaces_and_Page_Tables/Chapter_070_Page_Table_Debugging_and_Address_Translation_Evidence.md>`_。