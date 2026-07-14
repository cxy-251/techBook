项目状态
========

最后更新
--------

2026-07-14

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成：

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-082
   LK-WRITE-083..LK-WRITE-091
   LK-FORK-092..LK-FORK-094
   LK-COW-095..LK-COW-097

最新三章：

#. ``LK-COW-095``：child 写只读 COW 地址时，x86 #PF 怎样进入 do_wp_page？
#. ``LK-COW-096``：wp_page_copy() 怎样分配新 folio 并替换 child PTE？
#. ``LK-COW-097``：page fault 返回后，CPU 怎样重试 store 并完成 COW 隔离？

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

旧章节中的 ``Linux 6.12.95`` 是历史显示标签错误，技术事实继续以固定 Linux commit 为准。

已完成的运行期实验
------------------

#. cold-miss ``read(fd, buf, 4096)``；
#. ext4 ``O_SYNC write(fd, buf, 4096)``；
#. native x86-64 ``fork()``；
#. child private-anonymous COW write fault。

COW 固定场景
------------

::

   current task       = fork child
   userspace action   = store one 32-bit value to address A
   VMA                = private anonymous, VM_READ | VM_WRITE
   child PTE          = present, user, read-only
   parent PTE         = present, user, read-only
   old folio          = ordinary anonymous 4 KiB folio
   sharing            = parent and child both map old folio
   fault code         = X86_PF_PROT | X86_PF_WRITE | X86_PF_USER
   reuse              = impossible; wp_page_copy is required
   excluded           = THP, KSM, userfaultfd, swap, migration, zero page,
                        device-private page, pinning, pkey and shadow stack
   failure policy     = no allocation, memcg, copy, signal or OOM failure

完整控制流
----------

::

   child userspace store
   → x86 vector 14 #PF
   → asm_exc_page_fault / exc_page_fault
   → CR2 supplies address A
   → do_user_addr_fault
   → FAULT_FLAG_WRITE | FAULT_FLAG_USER
   → per-VMA lock fast path or mmap_read_lock fallback
   → handle_mm_fault
   → __handle_mm_fault
   → handle_pte_fault
   → present read-only PTE
   → do_wp_page
   → exclusive reuse rejected
   → folio_get(old)
   → release PTL
   → wp_page_copy
   → allocate and memcg-charge new 4 KiB folio
   → copy old folio contents
   → mark new folio uptodate
   → MMU notifier invalidate start
   → reacquire PTL and revalidate old PTE
   → ptep_clear_flush child old mapping
   → add exclusive anonymous rmap and LRU state
   → install writable, young, dirty child PTE
   → remove child rmap from old folio
   → MMU notifier invalidate end
   → minor-fault accounting
   → irqentry_exit / IRETQ
   → CPU retries original store
   → store succeeds on child new folio

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current task：child；
* CPU mode：x86-64 CPL 3；
* current location：原 store之后的下一条用户指令；
* child virtual A：映射 new folio；
* child PTE：present、user、writable、young、dirty；
* child new folio：anonymous、uptodate、exclusive，包含修改后的值；
* parent virtual A：仍映射 old folio；
* parent PTE：present、user、read-only；
* parent old folio：保留原始内容；
* child ``min_flt``：增加 1；
* child ``maj_flt``：不变；
* COW store：complete；
* next runtime scenario：unselected。

关键边界
--------

#. VMA writable与 PTE writable是不同权限层次。
#. fork后的 write fault可能复用独占页；本场景通过父子仍共同映射固定为真正 copy分支。
#. 新 folio分配、PAGE_SIZE copy、PTE替换和用户 store重试是四个阶段。
#. ``ptep_clear_flush`` 只替换 child translation，不修改 parent页表。
#. ``wp_page_copy`` 返回时原用户 store仍未执行。
#. page fault返回使用 IRETQ，CPU在同一 RIP重试 faulting store。
#. child完成 COW后，parent PTE不自动恢复 writable。

下一任务
--------

当前没有已选定场景。优先候选是 child执行固定 ``execve()``：

::

   native execve
   → pathname lookup / open executable
   → search_binary_handler
   → load_elf_binary
   → new mm and ELF mappings
   → interpreter branch if dynamically linked
   → user stack, argv, envp and auxv
   → close-on-exec and signal state changes
   → old mm replacement
   → enter new userspace image

开始前必须固定 executable path、static/dynamic ELF、interpreter、argv/envp、credentials与文件缓存状态。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。
