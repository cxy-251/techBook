第九十五章：child 写只读 COW 地址时，x86 #PF 怎样进入 do_wp_page？
============================================================================

上一条 ``fork()`` 场景结束时，parent 与 child 已拥有不同的 ``mm_struct`` 和页表根，但固定 private anonymous page 仍由两个只读 PTE 映射到同一个 small anonymous folio。

本章固定一个独立场景：

.. code-block:: text

   current task         = fork 后的 child
   userspace action     = 向固定地址 A 写入一个 32-bit value
   VMA                  = private anonymous, VM_READ | VM_WRITE
   child PTE            = present, user, read-only
   parent PTE           = present, user, read-only
   mapped folio         = ordinary 4 KiB anonymous folio
   sharing              = parent 与 child 都仍映射该 folio
   excluded             = THP, KSM, userfaultfd, swap, migration, device-private,
                          zero page, GUP pin, pkey denial, shadow stack
   failure policy       = allocation、memcg charge 与 copy 均成功，无 signal/OOM

共享关系确保 child 不能直接复用旧 folio，最终必须进入 ``wp_page_copy()``。

CPU 为什么产生 protection page fault
------------------------------------

child 的 VMA 允许写入，但页表中的 PTE 被 ``fork()`` 设置成只读。CPU 执行 store 时，地址转换找到 present PTE，却发现 write bit 不允许写入，因此产生 vector 14 ``#PF``。

本次 hardware error code 固定为：

.. code-block:: text

   X86_PF_PROT  = 1   已找到 present translation，是权限冲突
   X86_PF_WRITE = 1   触发访问是写入
   X86_PF_USER  = 1   访问来自 CPL 3
   X86_PF_RSVD  = 0
   X86_PF_INSTR = 0
   X86_PF_PK    = 0
   X86_PF_SHSTK = 0

CPU 把 fault address 写入 ``CR2``，保存 faulting RIP、CS、RFLAGS、RSP、SS 与 error code，然后进入 ``asm_exc_page_fault``。saved RIP 仍指向没有完成的 store 指令；page fault 属于可重启的 fault，不会像普通函数调用一样自动跳到下一条用户指令。

``exc_page_fault`` 怎样取得 fault address
-----------------------------------------

``DECLARE_IDTENTRY_RAW_ERRORCODE(X86_TRAP_PF, exc_page_fault)`` 生成 x86 page-fault entry。固定场景不使用 FRED，所以 C handler 通过：

.. code-block:: c

   address = read_cr2();

取得地址 A，然后执行：

.. code-block:: text

   irqentry_enter(regs)
   → handle_page_fault(regs, error_code, address)

KVM asynchronous page fault、kernel-address fault、kmmio 与异常修复分支均不适用于当前普通用户地址。

``do_user_addr_fault`` 怎样建立 fault flags
-------------------------------------------

``handle_page_fault()`` 判断 A 位于用户地址空间，于是调用：

.. code-block:: c

   do_user_addr_fault(regs, error_code, address);

当前 task 有有效 ``mm``，page fault handling 没有被禁止，saved RFLAGS 中 IF=1。函数重新打开本地中断并记录通用 page-fault perf event。

error code 被转换为内存管理层 flags：

.. code-block:: text

   X86_PF_WRITE + user_mode(regs)
   → FAULT_FLAG_WRITE | FAULT_FLAG_USER

没有 ``FAULT_FLAG_INSTRUCTION``、``FAULT_FLAG_UNSHARE`` 或 userfaultfd flags。

VMA lock 与 mmap_lock 两条入口怎样汇合
--------------------------------------

用户 fault 首先尝试：

.. code-block:: c

   vma = lock_vma_under_rcu(mm, address);

当 ``CONFIG_PER_VMA_LOCK`` 可用且 fast path 成功时，后续 ``handle_mm_fault()`` 带 ``FAULT_FLAG_VMA_LOCK``。如果配置不支持、lookup 失败或需要 retry，则进入：

.. code-block:: text

   lock_mm_and_find_vma
   → mmap_read_lock(mm)
   → 查找包含 A 的 VMA

两条路径都得到同一个 private anonymous VMA。这里必须区分：

* PTE read-only 触发了硬件 fault；
* VMA 仍包含 ``VM_WRITE``，所以这次访问在进程地址空间语义上合法。

因此 ``access_error()`` 不发送 ``SIGSEGV``。PTE 的只读状态是 COW 机制，不是用户申请的只读映射。

``handle_mm_fault`` 为什么进入普通页表路径
-----------------------------------------

``handle_mm_fault()`` 验证 ``FAULT_FLAG_WRITE`` 与 VMA 权限，进入 memcg user-fault accounting，然后调用：

.. code-block:: c

   __handle_mm_fault(vma, address, flags);

当前不是 hugetlb，也不是 THP PMD/PUD mapping。PGD、P4D、PUD、PMD 与 PTE page 均已在 fork 时建立，因此函数沿 child 的现有页表向下走到：

.. code-block:: c

   handle_pte_fault(&vmf);

``vmf.address`` 是 page-aligned A，``vmf.real_address`` 保存原始字节地址。

``handle_pte_fault`` 怎样识别 write-protected present PTE
--------------------------------------------------------

函数先 lockless 读取 child PTE：

.. code-block:: c

   vmf->orig_pte = ptep_get_lockless(vmf->pte);

当前 entry：

.. code-block:: text

   present = 1
   user    = 1
   write   = 0
   protnone= 0

所以不进入 missing、swap 或 NUMA ``PROT_NONE`` 分支。随后取得 page-table lock，重新验证 live PTE 仍与 ``orig_pte`` 相同。

因为 fault 带 ``FAULT_FLAG_WRITE`` 且 ``pte_write(entry) == false``：

.. code-block:: c

   return do_wp_page(vmf);

到这里，PTE lock仍由当前 child fault path 持有。

``do_wp_page`` 为什么不能复用旧 folio
------------------------------------

``do_wp_page()`` 排除 userfaultfd write-protect，随后通过：

.. code-block:: c

   vmf->page = vm_normal_page(vma, address, vmf->orig_pte);
   folio = page_folio(vmf->page);

取得旧 anonymous folio。

当前 VMA 不是 ``VM_SHARED``，所以进入 private mapping 逻辑。内核只有在以下条件成立时才可直接 ``wp_page_reuse()``：

.. code-block:: text

   PageAnonExclusive(page)
   或
   wp_can_reuse_anon_folio(folio, vma) == true

固定 old folio仍同时映射在 parent 与 child，引用与 mapcount 足以证明它不是 child 独占对象。因此：

.. code-block:: text

   PageAnonExclusive = false
   wp_can_reuse_anon_folio = false

内核不能只把 child PTE 改成 writable，否则 child 的 store 会直接修改 parent仍可读取的同一物理页。

``do_wp_page`` 怎样交给复制路径
------------------------------

函数先为 old folio增加临时引用：

.. code-block:: c

   folio_get(folio);

然后释放 child PTE mapping 与 page-table lock：

.. code-block:: c

   pte_unmap_unlock(vmf->pte, vmf->ptl);

物理页分配和 4 KiB copy 可能睡眠，不能持有 PTL 执行。最后进入：

.. code-block:: c

   return wp_page_copy(vmf);

当前精确边界
------------

CPU 正在 child 的 page-fault kernel context 中进入 ``wp_page_copy()``。

当前状态：

* current task：child；
* CPU mode：CPL 0，exception context 已转换为可睡眠的 user-fault handling；
* saved user RIP：仍指向原 store；
* fault flags：``FAULT_FLAG_WRITE | FAULT_FLAG_USER``；
* child VMA/mm：已锁定；
* child PTE lock：已释放；
* child PTE：仍指向 old folio且只读；
* parent PTE：仍指向 old folio且只读；
* old folio：父子共享，并由 fault path 持有临时引用；
* new folio：尚未分配；
* 用户 store：尚未完成；
* signal：未产生。

关键边界
--------

#. VMA writable 与 PTE writable 是不同权限层次。
#. ``X86_PF_PROT`` 表示 present translation 的权限错误，不表示地址无 VMA。
#. VMA-lock fast path 与 mmap-lock fallback 最终进入同一个 ``handle_mm_fault()``。
#. fork 后第一次写不一定复制；只有排除 exclusive reuse 后才能写死 ``wp_page_copy()``。
#. 分配和复制前必须释放 PTE lock，但 fault path仍持有 old folio引用和 VMA/mm保护。
#. saved RIP仍指向 faulting store，真正的用户写入尚未发生。

资料
----

* `Linux 7.2-rc1 arch/x86/include/asm/idtentry.h：page-fault entry declaration <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/idtentry.h>`_
* `Linux 7.2-rc1 arch/x86/mm/fault.c：exc_page_fault 与 do_user_addr_fault <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/fault.c>`_
* `Linux 7.2-rc1 mm/memory.c：handle_mm_fault、handle_pte_fault 与 do_wp_page <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/memory.c>`_
