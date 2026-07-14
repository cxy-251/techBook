第九十七章：page fault 返回后，CPU 怎样重试 store 并完成 COW 隔离？
================================================================================

第九十六章结束时，child 页表已经安装 writable PTE，指向新复制的 anonymous folio；parent仍通过只读 PTE映射 old folio。此时 COW page-table转换已经完成，原用户 store仍停在 saved RIP，尚未真正写入数据。

本章追踪 fault handler收尾、minor-fault accounting、异常返回与 CPU instruction retry，最后确认 parent和 child观察到不同物理页内容。

``handle_mm_fault`` 怎样记录一次 minor fault
-------------------------------------------

``wp_page_copy()`` 成功返回 0，控制权依次回到：

.. code-block:: text

   do_wp_page
   → handle_pte_fault
   → __handle_mm_fault
   → handle_mm_fault

本次没有磁盘读取、swap-in或等待外部 I/O，也没有返回 ``VM_FAULT_MAJOR``。``mm_account_fault()`` 因此：

.. code-block:: text

   current->min_flt += 1
   current->maj_flt 不变

COW copy需要分配和复制物理页，但仍属于 minor page fault；major/minor区分的核心不是“工作量大小”，而是是否需要 major-fault语义中的外部 backing I/O或相应 retry状态。

VMA/mm lock 怎样释放
--------------------

如果 fault使用 per-VMA lock fast path，``do_user_addr_fault()`` 在没有 ``VM_FAULT_RETRY`` 或 ``VM_FAULT_COMPLETED`` 时执行 ``vma_end_read(vma)``。

如果 fault使用 mmap-lock fallback，则在成功后执行：

.. code-block:: c

   mmap_read_unlock(mm);

两条路径都在离开 ``do_user_addr_fault()`` 前释放地址空间读取保护。当前没有 ``VM_FAULT_ERROR``，所以不会进入 OOM、SIGBUS 或 SIGSEGV处理。

``handle_page_fault`` 为什么再次关闭中断
---------------------------------------

``do_user_addr_fault()`` 为允许可睡眠的 fault handling重新打开了本地中断。返回后，``handle_page_fault()`` 执行：

.. code-block:: c

   local_irq_disable();

低级 exception-exit代码要求进入既定的中断状态，再由 ``irqentry_exit()`` 按 saved context统一恢复。这里关闭中断不是让 child永久禁用中断；用户态 RFLAGS会在异常返回时恢复。

page-fault exception 怎样返回用户态
------------------------------------

``exc_page_fault()`` 完成：

.. code-block:: text

   handle_page_fault
   → instrumentation_end
   → irqentry_exit
   → low-level exception return

普通 x86-64 IDT exception return恢复 child 的通用寄存器和硬件保存 frame，并通过 ``swapgs_restore_regs_and_return_to_usermode`` 路径返回。启用 PTI 时，返回代码切换回 child user CR3，恢复 user GS state，最终执行：

.. code-block:: asm

   iretq

这不是 syscall fast return，因此不使用 ``SYSRETQ``。page fault由 IDT exception进入，也由 IRET frame返回。

为什么 ``iretq`` 回到原 store，而不是下一条指令
-----------------------------------------------

CPU产生 page fault时保存的是 faulting instruction的 RIP。内核没有修改 ``regs->ip``，因此 ``iretq`` 恢复的仍是原 store地址。

控制流是：

.. code-block:: text

   第一次执行 store
   → child PTE只读
   → #PF
   → 内核复制 folio并安装 writable PTE
   → IRETQ恢复同一个 RIP
   → CPU重新执行同一条 store

exception handler并不代替 CPU写入用户指定的 value；它只修复让该指令能够成功执行的地址转换状态。

CPU 重试时为什么不再 fault
--------------------------

child 当前页表中地址 A 的 PTE已经是：

.. code-block:: text

   present = 1
   user    = 1
   write   = 1
   points to new folio

第九十六章中的 ``ptep_clear_flush()`` 已失效 child 对 old folio的 stale TLB translation。CPU重新做 translation时取得 new writable PTE，因此原 store成功完成。

x86硬件可更新 accessed/dirty状态；内核已经在创建 PTE时预设 young/dirty，因此无需再次进入 write-protection fault。

真正的数据变化发生在何时
------------------------

new folio在 PTE替换时仍保存 old folio的完整副本。只有 CPU重试 store后，目标 4 bytes才变成用户指定的新值：

.. code-block:: text

   parent old folio : 原始 4096-byte内容
   child  new folio : 原始内容 + 本次 store修改的目标字节

这一步才完成用户程序语义上的写入。

parent 为什么看不到 child 修改
-----------------------------

parent页表从未在 child fault中改成 new folio：

.. code-block:: text

   parent virtual A
   → parent read-only PTE
   → old folio

   child virtual A
   → child writable PTE
   → new folio

相同虚拟地址现在通过不同 ``mm`` 和不同页表根解析到不同物理页。child 的 store只修改 new folio，parent随后读取 A仍得到原值。

parent PTE 为什么仍可能只读
---------------------------

child COW完成后，old folio通常只剩 parent mapping，但 child fault path没有直接修改 parent页表。parent PTE仍保持 fork时的只读状态。

如果 parent未来也写 A，它可能再次产生 write fault。届时内核可根据 old folio最新 refcount/mapcount与 exclusivity状态选择：

* 直接 ``wp_page_reuse()``；
* 或再次 ``wp_page_copy()``。

这属于另一个独立运行期场景，不能在本章写死。

当前精确状态
------------

原 child store已经成功，CPU继续执行 store之后的下一条用户指令。

当前状态：

* current task：child；
* CPU mode：x86-64 CPL 3；
* child virtual A：映射 new folio；
* child PTE：present、user、writable、young、dirty；
* child new folio：anonymous、uptodate、exclusive mapping，包含修改后的值；
* parent virtual A：仍映射 old folio；
* parent PTE：present、user、read-only；
* parent old folio：保留 fault前内容；
* child ``min_flt``：增加 1；
* child ``maj_flt``：不变；
* signal：无；
* user store：complete；
* COW write-fault scenario：complete。

关键边界
--------

#. COW allocation/copy成功不等于用户 store已经完成，必须等待 exception return后的 instruction retry。
#. page fault返回使用 IRETQ，不是 syscall SYSRETQ。
#. minor fault仍可包含物理页分配和 PAGE_SIZE copy。
#. child TLB flush只针对 child mm的旧 translation；parent mapping保持不变。
#. parent和 child的虚拟地址相同，不代表 fault后仍指向同一物理页。
#. child COW不会主动把 parent PTE改回 writable；parent未来写入仍是独立 fault场景。

资料
----

* `Linux 7.2-rc1 arch/x86/mm/fault.c：page-fault handler收尾 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/fault.c>`_
* `Linux 7.2-rc1 arch/x86/entry/entry_64.S：用户异常返回与 IRETQ <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/entry_64.S>`_
* `Linux 7.2-rc1 mm/memory.c：handle_mm_fault accounting 与 COW完成 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/memory.c>`_
