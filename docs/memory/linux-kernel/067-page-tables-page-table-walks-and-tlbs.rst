第067章：页表、页表遍历与 TLB
=============================

本章必须记住
------------

#. 页表把虚拟页映射到物理页框，并把读、写、执行、用户访问和存在状态编码成硬件可检查的权限。
#. 虚拟地址通常拆成多级页表索引和页内偏移；页内偏移在翻译后保持不变。
#. ``mm_struct->pgd`` 是用户地址空间的顶层页表入口。
#. Linux 通用页表模型使用 PGD、P4D、PUD、PMD、PTE 五级名称。
#. 具体架构可以折叠某些层级；五级软件接口不表示所有 CPU 都执行五次真实页表读取。
#. PGD 是顶层目录，PTE 通常是普通页映射的叶子层，P4D、PUD、PMD 是中间层。
#. 大页可以在 PUD 或 PMD 等中间层形成叶子映射，不一定继续走到 PTE。
#. 每一级表项可能处于缺失、坏表项、指向下一级、形成大页映射或携带特殊状态等情况。
#. ``pte_t``、``pmd_t`` 等类型和具体位布局由架构定义，通用代码通过 ``pte_present()``、``pte_write()``、``set_pte_at()`` 等接口操作。
#. Present 位表示页表项当前可用于地址转换；not-present 不等于地址一定非法，还可能需要缺页分配、文件装入或 swap 换入。
#. User、writable、executable 等权限位让 CPU 在访存时执行内核建立的隔离策略。
#. 页表项中的 PFN 指向物理页框；PFN 与页内偏移共同形成最终物理地址。
#. 页表同时是翻译结构和权限结构，是内核内存策略的硬件可执行形式。
#. 硬件 page-table walk 发生在 TLB miss 后，由 MMU 按当前页表根逐级查表。
#. 软件 page-table walk 用于缺页处理、修改权限、回收映射、迁移页面和调试检查。
#. CPU 访存通常先查询 TLB；TLB 命中时无需重新遍历页表。
#. TLB 缓存虚拟页到物理页框的翻译及相关权限，目的是降低地址转换成本。
#. 修改页表后，旧 TLB 项可能继续存在，因此页表更新协议必须包含合适的 TLB invalidation。
#. 清除 PTE 但不刷新相关 TLB，CPU 可能继续使用旧映射，形成权限绕过或 use-after-free。
#. TLB flush 粒度可以是单页、地址范围、整个地址空间或更广范围，选择取决于修改规模和架构能力。
#. ``flush_tlb_page()``、``flush_tlb_range()``、``flush_tlb_mm()`` 等接口表达不同失效范围，具体实现由架构提供。
#. 多 CPU 同时运行同一 ``mm_struct`` 时，页表改变可能需要向其它 CPU 发送 TLB shootdown IPI。
#. TLB shootdown 会产生跨 CPU 中断、同步等待和缓存扰动，是频繁映射修改的重要成本。
#. ASID、PCID 等地址空间标签允许 TLB 同时保存不同地址空间的转换，减少上下文切换时全量失效。
#. 标签不能消除页表修改后的失效要求；它只帮助区分不同地址空间的缓存项。
#. 页表页本身也占用物理内存，``pgtables_bytes`` 等统计用于观察页表开销。
#. Page-table lock 保护页表结构更新；不同层级和架构可能使用更细粒度锁。
#. 页表锁只序列化软件修改，不自动等待正在使用旧翻译的 CPU；TLB flush 才收束硬件缓存。
#. 建立映射时通常先准备页面和下级页表，再按架构要求发布叶子表项。
#. 撤销映射时通常先清除页表项、执行必要失效，再释放旧页面或页表页。
#. ``mmu_gather`` 一类批处理机制可以聚合 unmap 和 TLB flush，减少逐页 shootdown 成本。
#. Huge page 和 THP 能减少页表层级、PTE 数量和 TLB 压力，但增加分配、拆分和回收复杂度。
#. Page fault 表示当前页表和访问权限不能直接完成本次访问，不必然表示程序错误。
#. 解释一次地址翻译必须同时知道架构、页大小、页表级数、当前 ``mm_struct``、大页状态和权限位。
#. 只看页表内容还不够；并发修改时必须持有正确锁或使用专门的 page-table walk 接口。

必背路径
--------

硬件地址翻译：

::

   CPU 产生虚拟地址
   → 查询 TLB
   → TLB 命中时得到 PFN 与权限
   → TLB 未命中时从当前页表根开始
   → PGD → P4D → PUD → PMD → PTE
   → 检查 present 与访问权限
   → 组合 PFN 和页内偏移
   → 缓存结果到 TLB
   → 访问物理内存

页表缺失或权限失败：

::

   页表 walk 无法完成访问
   → CPU 产生 page fault
   → 内核取得故障地址和错误码
   → 查找覆盖地址的 VMA
   → 判断访问是否合法
   → 分配匿名页、装入文件页、执行 COW 或换入 swap
   → 设置新页表项
   → 刷新必要 TLB 状态
   → 返回并重试原指令

撤销一个映射：

::

   在地址空间锁和页表锁下定位表项
   → 清除或替换 PTE / 大页表项
   → 记录需要失效的地址范围
   → 执行本地和远端 TLB invalidation
   → 确认旧翻译不再可用
   → 归还物理页和页表页引用

分析 TLB shootdown：

::

   找到修改页表的 mm 和范围
   → 确认哪些 CPU 正在使用该 mm
   → 发送远端失效 IPI
   → 各 CPU 清除对应 TLB 项
   → 等待完成确认
   → 再安全复用或释放旧页面

必须区分
--------

VMA 权限与页表权限
   VMA 保存范围级策略；页表项保存当前硬件实际执行的页级权限。

软件五级模型与硬件层级
   Linux 使用统一五级名称；架构可以折叠层级或在中间层形成大页映射。

页表与 TLB
   页表是内存中的权威映射结构；TLB 是 CPU 对页表翻译结果的缓存。

清除页表项与撤销访问
   软件表项改变后，旧 TLB 项仍可能生效；完成失效后才能认为硬件访问已撤销。

地址空间切换与页表修改
   切换 mm 改变当前翻译上下文；修改同一 mm 的映射需要针对相关 TLB 项失效。

Page fault 与非法地址
   Fault 可以是正常的延迟分配或 COW；只有 VMA 缺失或权限不允许等情况才形成用户错误。

一句话结论
----------

页表把内核的地址映射与权限策略交给 MMU 执行，TLB 缓存翻译结果；任何页表修改只有在相关 TLB 失效完成后才真正对所有 CPU 生效。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 14，Virtual Memory, Address Spaces, and Page Tables；
* AIBook 章节：Chapter 67，Page Tables, Page Table Walks, and TLBs；
* 源文件：``docs/LinuxK/Part_14_Virtual_Memory_Address_Spaces_and_Page_Tables/Chapter_067_Page_Tables_Page_Table_Walks_and_TLBs.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_14_Virtual_Memory_Address_Spaces_and_Page_Tables/Chapter_067_Page_Tables_Page_Table_Walks_and_TLBs.md>`_。