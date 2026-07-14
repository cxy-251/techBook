第一百章：start_thread() 怎样让 execve 进入新静态 ELF 的第一条指令？
================================================================================

第九十九章结束时，current task已经使用new exec mm，static ELF的 ``PT_LOAD`` VMAs、stack、argv、envp与auxv均已建立。入口text folio位于page cache，但new page tables中还没有entry PTE。

本章追踪：

.. code-block:: text

   finalize_exec
   → START_THREAD
   → 改写当前 syscall pt_regs
   → syscall exit到新 e_entry
   → instruction-fetch page fault
   → filemap_fault cache hit
   → 安装 executable PTE
   → 重试并执行新程序第一条指令

``finalize_exec`` 保存什么
--------------------------

``load_elf_binary()`` 调用：

.. code-block:: c

   finalize_exec(bprm);

它把exec过程中可能调整的 ``RLIMIT_STACK`` 写回当前process的signal state。此时新stack已经完成，旧程序的register state还保存在当前syscall的 ``pt_regs`` 中，下一步将被覆盖。

``START_THREAD`` 为什么不创建新的kernel thread
---------------------------------------------

x86-64 ``START_THREAD`` 最终调用：

.. code-block:: c

   start_thread(regs, elf_entry, bprm->p);

``regs`` 是当前exec syscall使用的 ``current_pt_regs()``。``start_thread_common()`` 修改：

.. code-block:: text

   regs->ip    = static ELF e_entry
   regs->sp    = new userspace stack pointer
   regs->cs    = __USER_CS
   regs->ss    = __USER_DS
   regs->flags = IF | fixed bit

同时清理旧程序遗留的FS/GS segment状态与architecture thread features。

这里没有创建新kernel stack、没有调用 ``wake_up_new_task()``，也没有scheduler handoff。仍是同一个child task，在同一个syscall kernel stack上准备返回用户态。

为什么成功的 execve 不返回旧调用点
----------------------------------

``load_elf_binary()`` 返回0后，控制流正常退出：

.. code-block:: text

   load_elf_binary
   → search_binary_handler
   → exec_binprm
   → bprm_execve
   → do_execveat_common
   → __x64_sys_execve
   → do_syscall_64

表面上像普通syscall返回，关键区别是 ``pt_regs`` 已被 ``start_thread()`` 改写。

因此 syscall-exit读取到的是：

.. code-block:: text

   RIP = new ELF e_entry
   RSP = new ELF userspace stack

而不是旧程序中 ``SYSCALL`` 后面的RIP/RSP。成功exec没有向旧image返回0；旧image已经不存在。

SYSRETQ 与 IRETQ 怎样选择
------------------------

``syscall_exit_to_user_mode()`` 完成pending work、signal与reschedule检查后，x86 exit code检查new RIP、RSP、selectors和RFLAGS是否满足fast return约束。

固定static ELF地址与stack都是canonical，通常可以走 ``SYSRETQ``；若任一安全条件不满足则走 ``IRETQ``。两条分支的architectural结果相同：

.. code-block:: text

   CPU mode = CPL 3
   RIP      = elf_entry
   RSP      = bprm->p
   address space = new exec mm

execve成功的语义不依赖具体使用SYSRETQ或IRETQ。

为什么第一条instruction仍会fault
--------------------------------

``elf_load()`` 通过mmap建立file-backed executable VMA，但没有使用 ``MAP_POPULATE``。new mm的entry地址尚无present PTE。

CPU返回CPL 3后尝试从 ``elf_entry`` fetch instruction，page walker发现PTE not present，于是产生vector 14 ``#PF``：

.. code-block:: text

   X86_PF_PROT  = 0   /* not-present */
   X86_PF_WRITE = 0   /* instruction fetch */
   X86_PF_USER  = 1
   X86_PF_INSTR = 1

CR2记录entry virtual address。异常入口是：

.. code-block:: text

   asm_exc_page_fault
   → exc_page_fault
   → handle_page_fault
   → do_user_addr_fault

``do_user_addr_fault`` 建立：

.. code-block:: text

   FAULT_FLAG_USER
   FAULT_FLAG_INSTRUCTION

VMA lookup找到具有 ``VM_READ | VM_EXEC`` 的text VMA，permission检查通过。

missing PTE 怎样进入 ext4 filemap fault
-------------------------------------

核心mm路径是：

.. code-block:: text

   handle_mm_fault
   → __handle_mm_fault
   → handle_pte_fault
   → do_pte_missing
   → do_fault
   → do_read_fault
   → __do_fault
   → vma->vm_ops->fault

第九十九章已经确认普通ext4 executable VMA使用：

.. code-block:: c

   ext4_file_vm_ops.fault = filemap_fault;

因此进入：

.. code-block:: c

   filemap_fault(vmf);

固定entry text folio已在page cache且uptodate，所以 ``filemap_fault`` 不构造READ bio，也不等待AHCI。它取得该folio reference并返回给generic fault completion。

``finish_fault`` 怎样安装 executable PTE
---------------------------------------

``finish_fault()`` 在child的新mm中取得PTE lock，确认entry仍是missing，然后根据text VMA protection构造PTE：

.. code-block:: text

   present = 1
   user    = 1
   young   = 1
   write   = 0
   execute = allowed because NX is clear

随后：

.. code-block:: text

   add file reverse mapping
   → install PTE
   → update_mmu_cache_range
   → unlock PTL

这不是COW：text mapping是 ``MAP_PRIVATE``，但当前是read/instruction fault，没有write request，也不创建anonymous copy。

为什么这是 minor fault
----------------------

所需text folio已经存在于page cache，fault没有等待storage I/O，所以返回值不包含 ``VM_FAULT_MAJOR``。

``mm_account_fault()`` 更新：

.. code-block:: text

   child->min_flt += 1
   child->maj_flt unchanged

page fault handler返回时，exception exit使用 ``IRETQ`` 恢复faulting userspace context。与普通syscall exit不同，page fault必须回到发生异常的同一 ``elf_entry`` RIP。

CPU 怎样真正执行第一条指令
--------------------------

CPU重试instruction fetch：

.. code-block:: text

   new page-table walk
   → present executable PTE
   → fetch bytes from cached text folio
   → execute instruction at ELF e_entry

现在static program才真正开始运行。其初始stack符合x86-64 ELF ABI：RSP指向argc，随后是argv、envp和auxv。C语言 ``main`` 通常还需要static runtime startup代码从 ``_start`` 解析这些结构后调用；kernel只负责进入 ``e_entry``，不会直接调用 ``main``。

当前精确状态
------------

* current task：原fork child，PID/TGID不变；
* CPU mode：x86-64 CPL 3；
* current RIP：static ELF ``e_entry`` 的第一条指令已经开始执行；
* current RSP：new userspace stack；
* ``current->mm``：new exec mm；
* old child mm与child COW folio mapping：已释放；
* parent mm与parent old folio：不变；
* executable text VMA：file-backed、private、read+execute；
* entry PTE：present、user、young、read-only、executable；
* entry text folio：page-cache resident、uptodate；
* entry instruction fault：minor fault，未发生storage I/O；
* fd 5：已关闭；
* task comm：已更新为 ``static-demo``；
* caught signal handlers：已重置；
* credentials：无提权变化；
* successful ``execve()``：complete；
* old execve call site：永远不会继续执行。

关键边界
--------

#. successful exec沿普通syscall return machinery退出，但pt_regs已经指向新image。
#. SYSRETQ或IRETQ都可能用于exec syscall exit；语义相同。
#. ELF mmap建立VMA不等于入口PTE已经present。
#. 首次instruction fault走filemap fault，不是anonymous fault或COW fault。
#. page-cache命中仍会产生minor page fault。
#. page fault通过IRETQ回到同一entry RIP，再重试instruction fetch。
#. kernel进入 ``e_entry``，不是直接进入C ``main``。

资料
----

* `Linux 7.2-rc1 fs/binfmt_elf.c：finalize_exec、START_THREAD 与 load_elf_binary结束路径 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/binfmt_elf.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/process_64.c：start_thread_common <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/process_64.c>`_
* `Linux 7.2-rc1 arch/x86/mm/fault.c：instruction page-fault入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/fault.c>`_
* `Linux 7.2-rc1 mm/memory.c：missing PTE、finish_fault 与PTE安装 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/memory.c>`_
* `Linux 7.2-rc1 mm/filemap.c：filemap_fault cache-hit路径 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/filemap.c>`_
