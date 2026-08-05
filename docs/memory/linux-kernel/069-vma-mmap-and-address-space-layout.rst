第069章：VMA、mmap 与地址空间布局
================================

本章必须记住
------------

#. ``struct vm_area_struct`` 表示一段连续虚拟地址范围的内存策略。
#. VMA 使用半开区间 ``[vm_start, vm_end)``，起点属于区域，终点不属于区域。
#. ``vm_start``、``vm_end`` 描述范围，``vm_mm`` 指向所属 ``mm_struct``。
#. ``vm_flags`` 描述读、写、执行、共享、增长、锁定和其它范围级属性。
#. ``vm_page_prot`` 把 VMA 权限转换成架构页表保护属性。
#. ``vm_file`` 非空时通常表示文件后端映射，匿名映射通常没有普通文件后端。
#. ``vm_pgoff`` 表示 VMA 起点对应的文件页偏移或特殊映射偏移。
#. ``vm_ops`` 提供 fault、open、close 等回调，使文件系统、驱动和特殊映射接管具体行为。
#. VMA 先定义地址范围的意义，物理页和 PTE 可以稍后才出现。
#. 地址落入 VMA 但 PTE 不存在时，访问可以触发合法缺页并建立映射。
#. 地址不落入任何 VMA 时，内核通常没有可用的范围策略，用户访问会形成映射缺失错误。
#. ``mmap`` 的主要动作是选择虚拟地址、计算权限和 flags、创建或合并 VMA，并把范围插入地址空间。
#. ``mmap`` 成功返回不表示所有页面已经分配、读入或建立 PTE。
#. Lazy allocation 把“保留虚拟范围”和“消耗物理页或读取文件”拆到不同时间点。
#. 匿名私有映射通常在首次写入时分配匿名页；初始读取可能使用共享零页等优化。
#. 文件映射首次访问时通常从 page cache 取得页面，必要时触发存储 I/O。
#. ``MAP_PRIVATE`` 表示修改对当前映射私有，写入通常通过 copy-on-write 形成匿名副本。
#. ``MAP_SHARED`` 表示多个映射者可以观察共享页面修改，并可能参与文件回写或共享内存协议。
#. ``PROT_READ``、``PROT_WRITE``、``PROT_EXEC`` 最终影响 VMA 标志和页表权限。
#. 用户请求的权限还受文件打开模式、挂载策略、W^X、安全模块和架构能力约束。
#. ``MAP_FIXED`` 会要求使用指定地址并可能替换已有映射，错误使用会破坏进程地址空间。
#. 普通地址 hint 不保证返回同一地址；内核会结合空洞、对齐、ASLR 和架构布局选择位置。
#. ``MAP_POPULATE`` 等选项可以请求提前填充页面，但不能把所有后续 fault 和回收可能性消除。
#. 一个 ``mmap`` 调用不一定对应一个独立 VMA；属性兼容的相邻范围可以合并。
#. VMA 是否可合并取决于权限、flags、文件、偏移、策略和回调等属性是否兼容。
#. ``mprotect`` 修改中间子范围时，原 VMA 可能被拆成左、中、右多个 VMA。
#. ``munmap`` 可以删除完整 VMA、截短 VMA，或删除中间范围并留下两侧映射。
#. 相邻 VMA 在修改后重新具有相同属性时，内核可以再次合并以减少对象数量。
#. 现代内核通常使用 Maple Tree 保存同一 ``mm_struct`` 中的不重叠 VMA 范围。
#. VMA 查找的目标是找到第一个覆盖地址或位于地址之后的区域，具体 API 以目标版本为准。
#. 修改 VMA 集合通常需要 ``mmap_lock`` 写侧保护；稳定遍历和 fault 路径使用相应读侧或专门协议。
#. VMA 指针不能在释放 ``mmap_lock`` 后长期保存，除非使用内核明确提供的稳定化或引用机制。
#. Page fault 路径先找 VMA，再检查访问类型与 ``vm_flags``，最后进入匿名、文件、COW 或特殊 ``vm_ops->fault`` 路径。
#. 文件后端的 ``vm_ops->fault`` 可以把设备页、文件页或特殊内存插入进程页表。
#. 驱动建立用户映射时必须同步设备对象、VMA 生命周期、页面 pin 和 remove 路径。
#. 匿名页通常通过 ``anon_vma`` 和反向映射关系连接到相关 VMA，供回收、迁移和 COW 使用。
#. 文件页通过 ``address_space`` 和 page cache 连接文件偏移、物理页面和多个进程映射。
#. 私有文件映射写入后，原文件页通常保持文件后端，当前进程得到匿名 COW 页。
#. 共享文件映射的脏页可能回写文件，具体时机由脏页、回写和 ``msync`` 等协议决定。
#. ``/proc/<pid>/maps`` 的每一行通常对应一个当前可观察的 VMA 范围或映射片段。
#. Maps 中的地址范围、权限、文件偏移和路径正是 VMA 范围策略的用户态投影。
#. VMA 数量过多会增加查找、修改和元数据成本，但数量本身不直接等于物理内存占用。
#. 调试映射问题时，应先看 VMA 范围与策略，再看具体页是否 present、swapped 或发生 COW。

必背路径
--------

创建文件映射：

::

   用户调用 mmap(fd, offset, length, prot, flags)
   → 内核验证长度、权限和文件能力
   → 选择虚拟地址空洞
   → 计算 vm_flags 与页表保护
   → 创建或合并 VMA
   → 保存 vm_file、vm_pgoff 和 vm_ops
   → 返回虚拟地址
   → 首次访问时 fault 装入文件页并建立 PTE

创建匿名私有映射：

::

   mmap(MAP_PRIVATE | MAP_ANONYMOUS)
   → 建立匿名 VMA
   → 初始时可以没有物理页
   → 首次读取使用零页或建立映射
   → 首次写入分配匿名页
   → 设置可写 PTE
   → 页面进入匿名反向映射与回收体系

修改中间一页权限：

::

   mprotect 指定 VMA 中间子范围
   → 在 mmap_lock 写侧定位原 VMA
   → 必要时拆出左侧 VMA
   → 建立中间权限 VMA
   → 必要时拆出右侧 VMA
   → 修改对应页表权限
   → 执行 TLB invalidation
   → 尝试合并属性再次相同的相邻 VMA

局部解除映射：

::

   munmap 指定地址范围
   → 查找所有重叠 VMA
   → 拆分边界 VMA
   → 从 Maple Tree 删除目标范围
   → 清除页表项
   → 刷新相关 TLB
   → 归还页面、文件和 VMA 资源

必须区分
--------

VMA 与物理页
   VMA 定义范围含义；物理页是某个虚拟页当前实际承载的数据。

``mmap`` 成功与页面驻留
   成功表示虚拟范围已经建立，页面仍可能在首次访问时才分配或读入。

``MAP_PRIVATE`` 与 ``MAP_SHARED``
   Private 写入通常形成 COW 私有页；shared 修改可以被其它映射者观察并可能回写后端。

文件映射与匿名映射
   文件映射从文件偏移和 page cache 取得内容；匿名映射由零页、匿名页和 swap 承载。

用户调用次数与 VMA 数量
   VMA 会合并和拆分，不能用 mmap 调用次数推断当前 VMA 数量。

VMA 权限与 PTE 权限
   VMA 保存范围策略；页表项保存当前每页实际硬件权限，两者必须一致更新。

一句话结论
----------

VMA 在页面出现之前就定义一段地址范围的权限、来源和 fault 策略；``mmap`` 创建这种范围语义，真正页面通常在后续访问中按需建立。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 14，Virtual Memory, Address Spaces, and Page Tables；
* AIBook 章节：Chapter 69，VMA, mmap, and Address Space Layout；
* 源文件：``docs/LinuxK/Part_14_Virtual_Memory_Address_Spaces_and_Page_Tables/Chapter_069_VMA_mmap_and_Address_Space_Layout.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_14_Virtual_Memory_Address_Spaces_and_Page_Tables/Chapter_069_VMA_mmap_and_Address_Space_Layout.md>`_。