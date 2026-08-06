第088章：fork 之后的写时复制
============================

本章必须记住
------------

#. ``fork`` 要求父子进程拥有语义独立的用户地址空间，但不要求立即复制所有物理页。
#. Linux 通过 Copy-on-Write（COW）把成本拆成：fork 时复制地址空间描述和页表关系，首次写入时再复制页面。
#. 父子进程各自拥有独立的 ``mm_struct``、VMA 集合和页表页，只有一部分叶子页表项暂时指向相同物理页。
#. VMA 复制负责保留虚拟地址范围、权限、匿名或文件后端以及 private/shared 语义。
#. ``copy_page_range()`` 一类路径复制已有页表映射并为需要 COW 的私有可写映射布置写保护。
#. 父进程原有 PTE 也必须被写保护，因为 fork 后父进程和子进程任意一方都可能首先写入共享页。
#. COW 的典型状态是：VMA 允许写，PTE 暂时不可写，写入由硬件 fault 转交内核处理。
#. PTE 不可写不能单独证明永久只读；必须同时检查 VMA 权限和映射是否属于 private COW。
#. 父子读取共享页不会复制内容，只要任一方没有执行会使页面分歧的写入。
#. 第一次写入共享私有页时，CPU 触发 write-protect fault，内核判断其是否属于合法 COW。
#. COW fault 通常分配新匿名页、复制原内容、更新写入方 PTE，并保留另一方对旧页的映射。
#. 写入方拿到可写私有页后，原用户指令被重新执行；父子随后看到不同内容。
#. 如果原页已经只剩当前地址空间独占，内核可能直接升级 PTE 写权限而不复制页面。
#. 是否可以原地复用取决于页类型、引用、mapcount、pin、KSM、swap 和其它状态，不能只看引用计数一个字段。
#. COW fault 通常属于 minor fault，因为页面内容已在内存中，但页分配和复制仍可能昂贵。
#. 复制成本与页面大小和写入范围相关；COW 一个 PMD-size THP 可能远重于复制一个基础页。
#. THP COW 可能复制整张大页、拆分后复制基础页或走版本相关优化，不能假设固定行为。
#. fork 本身的成本主要包括 task 创建、VMA 复制、页表复制、引用与写保护以及必要的 TLB 处理。
#. 父进程地址空间越大、已建立页表越多，fork 的页表复制成本越明显，即使物理数据尚未复制。
#. 未实际 fault 的 VMA 范围通常没有叶子 PTE，fork 不需要为这些未建立页面复制物理内容。
#. Fork 后大量写入会把延迟成本从 fork 时刻推迟到请求路径中的 COW faults。
#. 数据库、语言运行时和大内存服务在 fork 快照后继续写入，可能出现 RSS、内存带宽和 fault 数量快速增长。
#. Parent 和 child 的 RSS 都可能统计共享页面，简单相加会重复计算；PSS 更适合观察共享比例。
#. COW 后的新页计入写入进程的匿名私有内存，系统总物理占用随页面分歧增加。
#. ``MAP_SHARED`` 映射通常不使用 fork COW 来隔离写入，因为父子本来就应观察共享后端修改。
#. ``MAP_PRIVATE`` 匿名映射和文件私有映射都可使用 COW，但写入后的新页通常具有匿名私有语义。
#. 文件私有映射在 fork 前后可以共享 Page Cache folio；写 fault 后写入方获得匿名副本，不修改原文件。
#. 共享匿名映射在父子间继续共享，不应通过普通 COW 把写入隔离。
#. VMA 的 ``VM_DONTCOPY`` 等特殊标志可以影响某些映射是否进入子进程，具体规则以目标内核为准。
#. ``MADV_DONTFORK`` 可请求特定映射不继承给子进程；``MADV_WIPEONFORK`` 可要求子进程看到清零内容。
#. ``exec`` 会替换当前进程地址空间，fork 后立即 exec 的典型模式可避免大部分 COW 数据复制。
#. ``vfork`` 与 ``fork`` 的地址空间和父进程阻塞语义不同，不能把 vfork 当作普通 COW fork 使用。
#. 多线程进程 fork 后，子进程通常只保留调用 fork 的线程；用户态锁状态可能继承成危险快照。
#. COW 只解决内存页复制，不解决用户态互斥锁、文件描述符、信号和外部资源的一致状态。
#. 长期 GUP pin、DMA pin 和 writable pin 会改变页面能否安全 COW、迁移或回收，相关路径必须遵守 pin 协议。
#. 驱动不能缓存用户 PTE 对应的物理页并假设 fork 后写入仍指向同一页；用户地址映射可以因 COW 改变。
#. ``get_user_pages(FOLL_WRITE)`` 一类写 pin 需要触发或完成相应写权限和 COW 语义，具体 API 规则具有版本差异。
#. KSM 合并的相同匿名页也依靠写保护和 COW 在后续写入时重新分裂。
#. Swap 中的匿名页可在 fork 后被多个地址空间引用，swap-in 和 COW 需要共同维护引用和页表关系。
#. COW 更新 PTE 时必须持有页表锁并处理引用、反向映射、RSS、memcg、dirty 和 TLB 一致性。
#. 只替换 PTE 而不更新 mapcount、rmap 或旧页引用会造成 UAF、泄漏或回收错误。
#. Fault 路径可能因内存分配失败返回 OOM，COW 不是永远成功的透明操作。
#. Fork 后写入峰值可能超过 memcg 或系统容量，即使 fork 调用本身成功。
#. Overcommit 允许建立大地址空间不代表未来所有 COW 页面都有物理内存保证。
#. ``fork`` 返回成功只说明子进程和地址空间关系已建立，未来 COW 分配仍可能触发 reclaim、OOM 或延迟。
#. COW 性能排查应使用 fork 时间、minor fault 增量、RSS/PSS、匿名页增长、复制带宽和 THP split/copy 计数。
#. 只看 major faults 会漏掉 COW，因为 COW 通常不需要后端读入。
#. 只看 RSS 也无法区分共享页、私有 COW 页和文件 Page Cache，需要结合 smaps 字段。
#. ``Private_Dirty``、``Anonymous``、PSS 和 AnonHugePages 的变化可帮助定位 fork 后分歧。
#. 页表内存也可能随大量进程和大地址空间增长，应观察 ``VmPTE`` 或 smaps/statm 相关指标。
#. Fork-heavy workload 的优化方向包括减少父进程脏热页、fork 后尽快 exec、避免无关映射继承、调整 THP 策略或改变快照架构。
#. 关闭 THP 可能降低单次 COW 尖刺，也可能增加 TLB 和页表成本，必须用实际 workload 证据权衡。
#. 最稳定的 COW 阅读顺序是：fork 复制 mm/VMA → 复制并写保护 PTE → 父子读共享 → 首次写 fault → 页面复制或独占复用 → 更新写入方映射。

必背路径
--------

Fork 布置 COW：

::

   父进程调用 fork
   → 创建子 task_struct
   → 创建子 mm_struct
   → 复制父进程 VMA 语义
   → 遍历已有页表映射
   → private writable 页在父子 PTE 中写保护
   → 父子 PTE 暂时指向同一物理页
   → 更新页面引用和反向映射
   → 父子都可继续读取

子进程首次写入：

::

   子进程执行 store
   → PTE 不可写触发 page fault
   → VMA 允许 private write
   → 判断页面是否仍被共享
   → 不能独占时分配新匿名页
   → 复制旧页面内容
   → 子进程 PTE 指向新页并设为可写
   → 旧页仍供父进程读取
   → 刷新必要 TLB 并重试指令

独占页优化：

::

   COW write fault
   → 检查旧页类型、引用、mapcount 和 pin
   → 证明当前映射可安全独占
   → 不复制数据
   → 直接更新当前 PTE 为可写
   → 设置 dirty/accessed 状态
   → 返回并重试写入

Fork 后内存增长诊断：

::

   记录 fork 时间与 worker 数量
   → 采样 minor / major fault 增量
   → 读取 smaps 的 PSS、Private_Dirty、Anonymous
   → 检查 AnonHugePages 与 THP split/copy
   → 对齐父子写入时间线
   → 估算每次请求触碰的共享页数量
   → 判断 COW 放大、页表增长或其它匿名分配

Fork 后立即 exec：

::

   父进程 fork
   → 子进程只执行最小安全准备
   → exec 替换子进程 mm_struct 内容
   → 旧 COW VMA 和页表被销毁
   → 大部分父进程数据页从未发生复制
   → 新程序按自身 fault 建立地址空间

必须区分
--------

* 地址空间独立与物理页共享：父子拥有独立 mm/VMA/页表，只有部分叶子 PTE 暂时指向相同物理页。
* VMA 可写与 PTE 可写：COW 中 VMA 保留写语义，PTE 临时写保护以捕获首次写入。
* Fork 成本与 COW 成本：Fork 复制结构和页表关系；真实数据复制在后续写 fault 中发生。
* ``MAP_PRIVATE`` 与 ``MAP_SHARED``：Private 映射通过 COW 保持隔离；shared 映射的修改按共享后端语义传播。
* RSS 与物理独占内存：RSS 会包含共享映射；PSS 和 Private_Dirty 更适合区分共享和私有化程度。
* COW minor fault 与低成本：COW 通常计为 minor，但仍可能分配、复制大页、触发回收并形成明显延迟。

一句话结论
----------

Fork 的低成本来自父子页表暂时共享物理页并用写保护捕获分歧；真正的内存成本在后续写 fault 中按页面复制、独占复用或大页拆分逐步支付。
