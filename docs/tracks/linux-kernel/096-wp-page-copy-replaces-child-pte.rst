第九十六章：wp_page_copy() 怎样分配新 folio 并替换 child PTE？
============================================================================

第九十五章结束时，child 的 write fault 已进入：

.. code-block:: c

   wp_page_copy(vmf);

old folio仍由 parent 与 child 的只读 PTE共享。fault path 持有 old folio临时引用，但已经释放 child page-table lock。本章追踪新 folio分配、4 KiB copy、memcg/LRU/rmap 建立，以及 child PTE 的原子替换。

为什么先准备 anonymous VMA 元数据
--------------------------------

``wp_page_copy()`` 首先调用：

.. code-block:: c

   vmf_anon_prepare(vmf);

private anonymous folio必须挂入 ``anon_vma`` reverse-mapping体系。固定 VMA 已在 fork/原匿名页建立时拥有有效 ``anon_vma``，因此该调用直接成功，不需要放弃 per-VMA lock后重试 mmap-lock path。

随后确认 faulting PTE 不是 shared zero page：

.. code-block:: text

   pfn_is_zero = false

所以新页必须复制 old folio内容，而不是分配 zeroed folio后直接使用。

新 folio 怎样分配并计入 memcg
-----------------------------

``folio_prealloc()`` 根据 VMA 与 fault address 分配 ordinary movable anonymous folio，并执行 memcg charge。固定场景为 4 KiB small folio：

.. code-block:: text

   new folio order = 0
   size            = PAGE_SIZE = 4096
   owner mm        = child mm
   charge          = child 所属 memory cgroup

分配成功只得到尚未映射的新物理页。此时 child PTE 仍指向 old folio；parent 与 child的可见地址空间都尚未改变。

4 KiB 数据什么时候真正复制
--------------------------

``wp_page_copy()`` 调用：

.. code-block:: c

   __wp_page_copy_user(&new_folio->page, vmf->page, vmf);

普通 ``struct page`` 分支最终执行 ``copy_mc_user_highpage()``，把 old page 的完整 PAGE_SIZE 内容复制到 new page。

这次 copy发生在原用户 store重试之前：

.. code-block:: text

   old folio 原内容
   → CPU copy 4096 bytes
   → new folio相同内容
   → 稍后才重试用户 store

因此 COW 的含义不是“只复制用户即将修改的 4 bytes”，而是先复制整个 page，再让 faulting store修改 new folio中的目标字节。

copy完成后：

.. code-block:: c

   __folio_mark_uptodate(new_folio);

这表示 new folio内容已完整初始化，可安全建立用户映射。

为什么需要 MMU notifier 区间
----------------------------

在替换 child PTE 前，函数建立：

.. code-block:: c

   mmu_notifier_range_init(..., MMU_NOTIFY_CLEAR, child_mm,
                           page_start, page_start + PAGE_SIZE);
   mmu_notifier_invalidate_range_start(&range);

KVM、设备直通或其他 secondary MMU 用户可能缓存 child 虚拟地址到 old folio的映射。page-table lock不能替代 MMU notifier；两者保护不同观察者。

固定场景没有 notifier failure，但必须在替换后配对执行 ``mmu_notifier_invalidate_range_end()``。

为什么必须重新锁定并核对 PTE
----------------------------

分配和 copy期间没有持有 PTL。另一个执行者理论上可能改变 child PTE，因此函数重新取得：

.. code-block:: c

   vmf->pte = pte_offset_map_lock(child_mm, vmf->pmd,
                                  address, &vmf->ptl);

然后检查：

.. code-block:: c

   pte_same(current_pte, vmf->orig_pte)

固定 child 是单线程，没有 concurrent ``mprotect()``, ``munmap()`` 或另一个 fault，所以验证成功。若 PTE 已变化，内核会丢弃刚分配的新 folio并让现有映射获胜，不能覆盖更新后的页表状态。

新 child PTE 怎样构造
--------------------

函数从 new folio创建 PTE：

.. code-block:: c

   entry = folio_mk_pte(new_folio, vma->vm_page_prot);
   entry = pte_sw_mkyoung(entry);
   entry = maybe_mkwrite(pte_mkdirty(entry), vma);

固定 VMA包含 ``VM_WRITE``，所以新 entry 的关键状态是：

.. code-block:: text

   present = 1
   user    = 1
   write   = 1
   young   = 1
   dirty   = 1

PTE dirty bit在真正 store执行前就被设置。内核这样做是为了避免 write-fault、硬件 dirty-bit与后续页面状态之间的竞争；它不表示用户 store已经发生。

为什么先 clear+flush，再安装新 PTE
---------------------------------

child 的旧 PTE不能直接被 new PTE无序覆盖。内核先执行：

.. code-block:: c

   ptep_clear_flush(vma, address, vmf->pte);

该操作清除 child 的 old-folio PTE，并刷新 child mm 中该地址的旧 TLB translation。顺序要求是：

.. code-block:: text

   child old PTE clear
   → child TLB old translation invalidated
   → 建立 new folio rmap
   → 安装 child new PTE

如果先安装新 PTE再 flush，某些 CPU可能短时间同时缓存 old/new translation，破坏 mapcount与 page reuse判断。

new folio 怎样获得 exclusive anonymous rmap
-------------------------------------------

旧 translation清除后，内核执行：

.. code-block:: c

   folio_add_new_anon_rmap(new_folio, vma, address, RMAP_EXCLUSIVE);
   folio_add_lru_vma(new_folio, vma);

这里建立：

* new folio属于 child anonymous VMA；
* child PTE是它的第一个 reverse mapping；
* new folio对 child mm是 anonymous-exclusive；
* folio进入适用的 LRU/memcg管理结构。

随后：

.. code-block:: c

   set_pte_at(child_mm, address, vmf->pte, entry);
   update_mmu_cache_range(vmf, vma, address, vmf->pte, 1);

child 页表现在指向 new folio，并允许写入。

old folio 的 child rmap 为什么最后才删除
----------------------------------------

只有 child PTE 已经切换到 new folio后，内核才调用：

.. code-block:: c

   folio_remove_rmap_pte(old_folio, vmf->page, vma);

这会移除 old folio对应的 child mapping。顺序不能反过来：若先降低 old folio mapcount，另一个 fault可能判断 old folio已独占并允许写入，而 child 的 PTE仍短暂指向它。

完成后映射关系变为：

.. code-block:: text

   parent mm / read-only PTE → old anonymous folio

   child mm  / writable PTE  → new anonymous folio

parent 的页表完全没有在本次 child fault中被修改。

引用与锁怎样收尾
----------------

child PTE 安装后，函数释放 PTL，结束 MMU notifier区间，并释放临时 folio引用。

``wp_page_copy()`` 返回 0，表示 fault已经成功解决。返回值不是 copied-byte count；用户 store仍由 CPU在异常返回后重试。

当前精确边界
------------

``wp_page_copy()`` 已成功返回，控制权正沿 ``do_wp_page()``、``handle_pte_fault()`` 与 ``handle_mm_fault()`` 向 x86 fault entry返回。

当前状态：

* child PTE：present、user、writable、young、dirty，指向 new folio；
* new folio：4 KiB、uptodate、anonymous、exclusive to child、已加入 LRU/memcg；
* new folio内容：仍是 old folio在 fault前的完整副本；
* parent PTE：仍是只读，指向 old folio；
* old folio：已移除 child rmap，仍由 parent映射；
* child old TLB translation：已由 ``ptep_clear_flush()`` 失效；
* child PTE lock：已释放；
* MMU notifier：invalidate range已结束；
* child minor-fault accounting：将在 ``handle_mm_fault()`` 收尾时完成；
* 原用户 store：仍未执行成功。

关键边界
--------

#. 分配新 folio、复制数据和替换 PTE是三个独立步骤。
#. 4-byte store触发的是 PAGE_SIZE 数据复制。
#. new PTE 的 dirty bit可在用户 store重试前预先设置。
#. ``ptep_clear_flush()`` 只处理 child mm 的旧 translation，不修改 parent PTE。
#. new rmap建立后才能安全移除 old folio的 child rmap。
#. ``wp_page_copy()`` 返回 0表示 fault resolved，不表示用户指令已经完成。

资料
----

* `Linux 7.2-rc1 mm/memory.c：wp_page_copy、__wp_page_copy_user 与 do_wp_page <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/memory.c>`_
* `Linux 7.2-rc1 include/linux/mmu_notifier.h：MMU notifier invalidation protocol <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/mmu_notifier.h>`_
* `Linux 7.2-rc1 mm/rmap.c：anonymous reverse mapping <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/rmap.c>`_
