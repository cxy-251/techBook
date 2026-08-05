第087章：匿名内存与文件后备映射
================================

本章必须记住
------------

#. ``mmap`` 首先建立的是一段虚拟地址范围、访问权限和后端语义，不保证立即建立物理页和完整页表。
#. ``struct vm_area_struct`` 描述一段属性一致的虚拟地址范围，是匿名、文件、共享和私有语义的主要载体。
#. 判断 VMA 后端时，应先看 ``vm_file``、``vm_flags``、``vm_pgoff`` 和 ``vm_ops``，再看当前页表状态。
#. 匿名 VMA 通常没有普通文件后端，``vm_file`` 为 ``NULL``；堆、栈和 ``MAP_ANONYMOUS`` 映射属于常见来源。
#. 文件后备 VMA 通过 ``vm_file`` 连接 ``struct file``，再通过 ``f_mapping`` 连接文件的 ``address_space`` 和 Page Cache。
#. 匿名映射的初始内容语义是零，不表示创建 VMA 时已经为每个地址分配并清零物理页。
#. 匿名页通常在首次写 fault 时按需分配；只读 fault 可以使用共享零页或等价零值机制，具体实现具有架构和版本差异。
#. 共享零页只提供只读零内容；首次写入仍需分配进程可写匿名页。
#. 匿名页没有普通文件可重新读取，回收时需要 swap、zswap、内存分层或其它保存内容的机制。
#. ``anon_vma`` 和反向映射帮助内核追踪匿名页被哪些 VMA 与页表映射，用于 COW、回收和迁移。
#. 文件映射把虚拟地址偏移连接到文件偏移；``vm_pgoff`` 参与计算映射起点对应的文件页索引。
#. 普通文件映射首次访问时，fault 路径通常在 Page Cache 中查找对应 folio。
#. Page Cache 命中且 folio 可用时，只需安装进程页表映射，通常形成 minor fault。
#. Page Cache 未命中时，文件系统需要把后端内容读入 folio，通常形成 major fault。
#. 文件映射和普通 buffered ``read`` 可以共享同一个 Page Cache 对象，只是用户访问数据的方式不同。
#. ``read`` 通常从 folio 复制到用户缓冲区；``mmap`` 则把 folio 映射进进程页表，让 CPU 直接访问。
#. ``mmap`` 成功后关闭原文件描述符通常不会破坏映射，因为 VMA 已持有需要的文件对象引用。
#. 文件截断、打洞和失效操作必须与现有文件 VMA、Page Cache、页表和 writeback 协调。
#. 访问文件映射中超过当前有效文件后端的页，可能收到 ``SIGBUS``，不能把 VMA 范围存在等同于后端永远可读。
#. ``MAP_PRIVATE`` 表示写入通过 COW 形成调用进程私有副本，不把私有修改写回原文件。
#. 文件 ``MAP_PRIVATE`` 映射在只读阶段可以共享 Page Cache folio；第一次写入通常转成匿名私有页。
#. ``MAP_SHARED`` 表示多个映射可观察共享后端对象的修改；文件共享写入通常形成 Page Cache dirty folio。
#. ``MAP_SHARED`` 的可见性不等于立即持久化；``msync``、``fsync``、文件系统和设备语义决定写回边界。
#. ``MAP_SHARED | MAP_ANONYMOUS`` 没有普通文件后端，但可让相关进程共享同一匿名内存对象。
#. ``MAP_PRIVATE | MAP_ANONYMOUS`` 是进程私有按需匿名内存的常见形式，fork 后再通过 COW 暂时共享物理页。
#. VMA 的 ``VM_SHARED``、``VM_MAYWRITE``、``VM_WRITE`` 等内部标志表达当前和允许的权限边界，具体位名以目标源码为准。
#. ``PROT_READ``、``PROT_WRITE``、``PROT_EXEC`` 决定用户态允许的访问类型，页表权限由 VMA 语义和当前状态共同生成。
#. VMA 可写而 PTE 只读不一定是错误，可能是 COW、dirty tracking 或其它内核协议的暂时状态。
#. Demand paging 把页分配、文件读取和页表建立推迟到实际访问，提高稀疏地址空间和大保留范围的效率。
#. 虚拟地址空间大小可以远大于当前 RSS，因为未访问 VMA 不一定拥有驻留物理页。
#. RSS 增长通常发生在页面被实际 fault 并保持驻留后，而不是单纯创建 VMA 时。
#. ``MAP_POPULATE``、``mlock``、预取和应用主动触碰可以提前建立部分页面，但不改变映射后端的基本语义。
#. ``MAP_POPULATE`` 的完成和错误语义受映射类型与内核版本影响，不能把它当作所有页面永久驻留保证。
#. ``mlock`` 影响页面可回收性和驻留策略，不负责把无效地址或权限错误变成合法访问。
#. ``madvise`` 可以表达顺序访问、随机访问、大页偏好、丢弃或预取建议，具体结果仍由内核策略决定。
#. ``MADV_DONTNEED``、``MADV_FREE`` 等对匿名和文件映射的效果不同，使用前必须读取目标内核和映射类型语义。
#. ``munmap`` 删除 VMA 范围并解除页表映射，但物理页是否释放还取决于其它进程、Page Cache、引用和后端对象。
#. ``mprotect`` 修改 VMA 权限并更新页表保护，通常需要 TLB 失效和并发 fault 协调。
#. VMA 可以被拆分、合并和调整；保存裸 VMA 指针跨越锁释放或 fault retry 是不安全的。
#. 匿名页可以因 fork、KSM 或共享匿名映射被多个页表引用，不能按“匿名页必然只有一个进程”理解。
#. KSM 可以合并内容相同的匿名页并通过 COW 处理后续写入，是否启用和适用取决于策略。
#. 文件 Page Cache folio 也可以被多个进程页表同时映射；mapcount、引用和 Page Cache 所有权是不同关系。
#. ``MAP_SHARED`` 文件页的 dirty 状态属于文件缓存后端；单个进程退出不代表脏数据已经落盘。
#. ``MAP_PRIVATE`` 的匿名 COW 副本不属于原文件 writeback，退出或回收时按匿名页语义处理。
#. DAX、设备映射、PFNMAP、HugeTLB 和 userfaultfd 可以提供特殊 VMA fault 语义，不能机械套用 Page Cache 模型。
#. 用户态映射设备内存时，VMA 可能连接驱动 ``vm_ops`` 和 PFN，而非普通 ``struct page`` 或文件 folio。
#. 分析内存映射时，应先确认地址落在哪个 VMA、VMA 是 anonymous/file、private/shared，再分析 fault 和页表。
#. ``/proc/<pid>/maps`` 主要展示范围、权限、共享属性和文件路径；``smaps`` 进一步展示 RSS、PSS、dirty、anonymous 和 huge page 统计。
#. Maps/smaps 是瞬时用户态视图，不能单独证明某次 fault 是否等待了 I/O。
#. 运行时还需结合 minor/major fault、Page Cache、swap、writeback 和块层延迟建立完整证据链。
#. 最稳定的映射阅读顺序是：VMA 范围与权限 → anonymous/file 后端 → private/shared 语义 → 页表状态 → fault 后端 → 回收或回写。

必背路径
--------

匿名映射首次写入：

::

   mmap / brk / 栈建立匿名 VMA
   → 尚未建立目标地址 PTE
   → CPU 第一次写入
   → page fault 定位匿名 VMA
   → 分配并清零匿名 folio
   → 建立 anon_vma 与反向映射关系
   → 安装可写 PTE
   → 更新 RSS、LRU 和 memcg
   → 重试原指令

文件映射首次读取：

::

   mmap 建立文件后备 VMA
   → 访问映射地址
   → 用 vm_pgoff 与地址计算文件页索引
   → 通过 vm_file 找到 address_space
   → Page Cache 查找 folio
   → 命中时安装 PTE
   → 未命中时 read_folio / readahead 读入
   → folio uptodate 后安装映射

文件 ``MAP_PRIVATE`` 写入：

::

   初始 PTE 映射 Page Cache folio
   → VMA 允许私有写但 PTE 被写保护
   → 用户写入触发 COW fault
   → 分配匿名私有 folio
   → 复制原文件页内容
   → 当前进程 PTE 指向匿名副本
   → 原文件和其它进程映射不受私有修改影响

文件 ``MAP_SHARED`` 写入：

::

   VMA 连接共享文件映射
   → 写 fault 准备可写 Page Cache folio
   → 页表映射共享后端页
   → 用户修改 folio
   → folio 标记 dirty
   → 其它共享映射可观察修改
   → msync / writeback / fsync 提交文件后端

映射销毁：

::

   munmap 或进程退出
   → 阻止该范围新用户访问
   → 删除或调整 VMA
   → 清除页表映射并刷新 TLB
   → 解除匿名反向映射或文件 mapcount
   → 降低页面引用
   → 其它映射或 Page Cache 仍持有时保留页面
   → 最后引用结束后才可回收存储

必须区分
--------

VMA 建立与物理页建立
   ``mmap`` 先创建地址范围语义；物理页和 PTE 通常在后续访问时按需出现。

匿名映射与文件映射
   匿名页以零值和 swap 为后端语义；文件映射以文件偏移和 Page Cache 为后端。

``MAP_PRIVATE`` 与 ``MAP_SHARED``
   Private 写入形成私有 COW 副本；shared 写入修改共享后端并可能进入 writeback。

文件描述符与映射生命周期
   fd 是用户句柄；映射成功后 VMA 持有自己的文件对象关系，关闭 fd 通常不取消映射。

VMA 范围与后端有效范围
   地址可以位于 VMA 内，但文件截断或后端错误仍可能使 fault 返回 ``SIGBUS``。

RSS 与虚拟地址空间
   虚拟范围表示可访问语义；RSS 只统计当前驻留的部分页面。

一句话结论
----------

``mmap`` 的核心是先为虚拟地址建立匿名或文件、私有或共享的后端语义，实际页面再由 fault 按需连接到零页、匿名页、Page Cache 或 COW 副本。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 18，Memory Mapping, Page Faults, Copy-on-Write, and Huge Pages；
* AIBook 章节：Chapter 87，Anonymous Memory and File-Backed Mapping；
* 源文件：``docs/LinuxK/Part_18_Memory_Mapping_Page_Faults_Copy_on_Write_and_Huge_Pages/Chapter_087_Anonymous_Memory_and_File_Backed_Mapping.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_18_Memory_Mapping_Page_Faults_Copy_on_Write_and_Huge_Pages/Chapter_087_Anonymous_Memory_and_File_Backed_Mapping.md>`_。