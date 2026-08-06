第087章：匿名内存与文件后备映射
================================

核心知识点
----------

``mmap`` 先创建地址语义
   映射建立时，内核首先确定虚拟地址范围、访问权限、private/shared 属性和后端对象。物理页、PTE、Page Cache folio 或 swap 条目通常在后续访问中按需出现。

VMA 是映射语义的载体
   ``vm_start``、``vm_end`` 定义范围，``vm_flags`` 和 ``vm_page_prot`` 定义权限，``vm_file``、``vm_pgoff`` 和 ``vm_ops`` 连接具体后端与 fault 行为。

匿名映射没有普通文件后端
   堆、栈和 ``MAP_ANONYMOUS`` 通常由匿名 VMA 表示。初始内容语义为零，首次写入时才分配并清零匿名页，回收时需要 swap、内存分层或其它内容保存机制。

文件映射连接 Page Cache
   文件 VMA 通过 ``vm_file`` 找到 ``struct file``，再经 ``f_mapping`` 进入 ``address_space`` 和 Page Cache。文件偏移由地址、VMA 起点和 ``vm_pgoff`` 共同计算。

Demand paging 延迟真实成本
   大范围 VMA 可以存在而 RSS 很低，因为未访问页面没有驻留物理页。实际 fault 时才分配匿名页、读入文件页或安装已有缓存页的 PTE。

文件映射可产生 Minor 或 Major fault
   Page Cache 已有可用 folio 时，只需安装页表映射，通常是 minor fault；缓存未命中并需要后端读入时，通常是 major fault。

``MAP_PRIVATE`` 通过 COW 隔离写入
   私有文件映射初始可共享 Page Cache folio，首次写入后形成匿名私有副本。修改只对当前地址空间可见，不进入原文件的 writeback。

``MAP_SHARED`` 修改共享后端
   共享文件映射让多个映射者观察同一 Page Cache 内容，写入后 folio 进入 dirty 状态。共享可见性不等于已经持久化，写回边界仍由 ``msync``、``fsync`` 和文件系统决定。

映射生命周期独立于文件描述符
   ``mmap`` 成功后，VMA 持有需要的文件对象关系，关闭用户态 fd 通常不会取消映射。``munmap`` 或进程退出才移除对应地址范围。

VMA 范围不保证后端始终有效
   文件被截断、打洞或后端发生错误时，地址仍可能位于原 VMA 内，fault 却无法取得有效内容，最终可能产生 ``SIGBUS``。

页面所有权与页表映射不同
   文件 folio 可由 Page Cache 和多个进程共同持有；匿名页也可因 fork、KSM 或共享匿名映射被多个页表引用。Mapcount、普通引用和后端所有权必须分别维护。

特殊映射使用不同协议
   DAX、PFNMAP、设备内存、HugeTLB、shmem 和 userfaultfd 可以提供自己的 ``vm_ops``、PFN 或页表语义，不能机械套用普通匿名页或文件 Page Cache 模型。

关键路径
--------

匿名映射首次写入：

::

   mmap、brk 或栈建立匿名 VMA
   → 目标地址尚无可写 PTE
   → 用户写入触发 page fault
   → 验证 VMA 允许匿名写
   → 分配并清零匿名 folio
   → 建立 anon_vma 与反向映射
   → 安装可写 PTE
   → 更新 RSS、LRU 和 memcg

文件映射首次读取：

::

   mmap 建立文件后备 VMA
   → 访问映射地址
   → 计算文件页索引
   → 经 vm_file 找到 address_space
   → Page Cache 查找 folio
   → 命中时直接安装 PTE
   → 未命中时由文件系统读入
   → folio 可用后建立映射

Private 与 Shared 写入：

::

   文件页当前已映射
   → Private 写 fault 分配匿名副本并切换当前 PTE
   → Shared 写 fault 保持共享 Page Cache 后端
   → Shared folio 被标记 dirty
   → 后续 writeback 或同步接口提交文件

概念辨析
--------

* VMA 建立与页面建立：VMA 先定义地址范围语义；页面和 PTE 通常由后续 fault 按需构造。
* 匿名映射与文件映射：匿名页以零值和 swap 为后端；文件映射以文件偏移和 Page Cache 为后端。
* ``MAP_PRIVATE`` 与 ``MAP_SHARED``：Private 写入形成匿名 COW 副本；Shared 写入修改共享后端并参与回写。
* 文件描述符与映射：fd 是用户句柄；映射成功后，VMA 持有独立的文件对象关系。
* VMA 范围与后端有效范围：地址落在 VMA 内，不保证文件当前仍能提供对应内容。
* 页表映射与页面所有权：撤销一个 PTE 只结束一个映射关系，页面是否释放还取决于其它映射、引用和后端对象。

本章结论
--------

``mmap`` 的核心是先为地址建立匿名或文件、私有或共享的后端语义。实际页面随后由 fault 连接到零页、匿名页、Page Cache、swap 或 COW 副本。
