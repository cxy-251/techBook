第九十三章：copy_process() 怎样复制资源并建立 COW 子进程？
=================================================================

第九十二章结束时，新 ``task_struct`` 和 kernel stack 已经分配，scheduler把 child保持在 ``TASK_NEW``。``copy_process()`` 接下来必须把父进程的 process environment拆分成一组明确的复制或共享关系。

固定普通 fork满足：

.. code-block:: text

   clone_flags = 0

因此本章中的主线是：

* 新建 files、fs、sighand、signal和 mm对象；
* namespace对象按引用继承；
* VMA metadata被复制；
* writable private present page通过只读页表建立 COW；
* 新 PID、用户寄存器 frame和 process-tree关系被发布；
* child仍保持 ``TASK_NEW``，尚未进入 runqueue。

``copy_files`` 为什么既复制 fd table又共享 open file description
-------------------------------------------------------------

普通 fork没有 ``CLONE_FILES``，所以：

.. code-block:: c

   newf = dup_fd(current->files, NULL);
   p->files = newf;

parent与 child获得不同的 ``struct files_struct`` 和 fd table。随后双方可以分别执行 ``close()``、``dup()`` 或扩展自己的 descriptor table，而不会直接改动对方表中的 slot。

每个已打开 fd指向的 ``struct file`` 并不会被深复制。``dup_fd()`` 增加 file references，使父子 fd entry继续指向同一个 open file description。因此普通 fork后仍然共享：

* ``struct file`` 中的 file position；
* open status flags；
* filesystem维护的 open-file状态。

“fd table独立”与“open file description共享”是两个不同层次。

``copy_fs`` 怎样处理 cwd、root和 umask
-------------------------------------

普通 fork没有 ``CLONE_FS``，``copy_fs()`` 调用 ``copy_fs_struct()``，建立新的 ``struct fs_struct``。

child继承父进程当前：

* root path；
* current working directory；
* umask。

新 ``fs_struct`` 内部对 path对象增加引用。fork之后 parent与 child可以分别 ``chdir()``、``chroot()`` 或修改 umask，而不会因为共享同一个 ``fs_struct`` 自动改变另一方。

``copy_sighand`` 与 ``copy_signal`` 为什么都要存在
------------------------------------------------

signal相关状态不是一个对象。

``copy_sighand()`` 为 child分配新的 ``struct sighand_struct``，在父 ``siglock`` 下复制 signal action table：

.. code-block:: text

   SIG_DFL / SIG_IGN / userspace handler
   signal masks and action flags

``copy_signal()`` 则为新的 thread group创建 ``struct signal_struct``，初始化：

* ``nr_threads = 1``；
* shared pending queue；
* child-exit wait queue；
* resource limits；
* POSIX CPU timers；
* tty、OOM与 group-level bookkeeping。

普通 fork不是 ``CLONE_THREAD``，所以 child成为自己 thread group的唯一线程。signal handlers的内容被复制，sighand与 signal对象本身不和 parent共享。

``copy_mm`` 为什么必须创建新的 ``mm_struct``
-----------------------------------------

普通 fork没有 ``CLONE_VM``。``copy_mm()`` 因而不增加父 mm的 ``mm_users`` 后直接共享，而是调用：

.. code-block:: c

   mm = dup_mm(p, current->mm);

``dup_mm()``：

#. 分配新的 ``struct mm_struct``；
#. 初始化新的 page-global-directory、mmap lock、RSS counters和 architecture mm context；
#. 调用 ``dup_mmap(new_mm, old_mm)``；
#. 把新 mm安装到 ``p->mm`` 与 ``p->active_mm``。

parent与 child从此拥有不同的 mm对象和不同的页表根。fork并没有让两个 task永久共享同一套页表。

``dup_mmap`` 怎样复制 VMA topology
---------------------------------

``dup_mmap()`` 取得父 mm和新 mm的 mmap write locks，并复制父 mm的 Maple Tree topology。它随后遍历每个父 VMA，为 child建立新的 ``struct vm_area_struct``。

固定场景排除：

* ``VM_DONTCOPY``；
* ``VM_WIPEONFORK``；
* hugetlb与 THP特殊分支；
* userfaultfd；
* pinned-page立即复制；
* swap、migration和 device-private entries。

对普通 VMA，函数复制：

* address range；
* protection和 vm flags；
* anonymous-vma关系；
* file mapping引用与 interval-tree linkage；
* memory policy和 vm operations。

VMA metadata复制完成后，``copy_page_range(child_vma, parent_vma)`` 处理实际页表 entries。

COW 为什么要先修改父页表
------------------------

固定 private anonymous VMA包含一个 present、writable PTE，映射 anonymous folio ``F``。该 VMA属于 copy-on-write mapping。

``copy_present_ptes()`` 最终进入：

.. code-block:: c

   if (is_cow_mapping(src_vma->vm_flags) && pte_write(pte)) {
       wrprotect_ptes(src_mm, addr, src_pte, nr);
       pte = pte_wrprotect(pte);
   }

这里发生两件事：

#. 父进程原本 writable 的 PTE被 write-protect；
#. 写入 child页表的 PTE也被 write-protect。

父页表必须一起修改。只把 child设成只读会允许 parent继续无 fault地改写共享物理页，从而破坏 fork时父子独立地址空间的语义。

物理页为什么没有立即复制
------------------------

普通未 pin 的 anonymous folio不走 ``copy_present_page()`` 的立即复制分支。内核增加 folio reference和 reverse mapping，让 parent与 child的两个只读 PTE都指向同一个物理 folio：

.. code-block:: text

   parent mm / parent PTE --read-only--┐
                                      ├→ anonymous folio F
   child mm  / child PTE  --read-only--┘

此时复制的是：

* child VMA；
* child page-table pages；
* PTE values与引用关系。

没有复制 folio ``F`` 中的 4096 bytes。真正的 data-page copy留到某一方未来对该私有页执行 write并触发 COW page fault时发生。

``flush_tlb_mm(oldmm)`` 为什么在复制后执行
----------------------------------------

``dup_mmap()`` 修改了父进程页表中的 writable PTE。CPU TLB可能仍缓存旧 writable translation，所以函数在解锁前后执行必要的 cache/TLB同步，最终：

.. code-block:: c

   flush_tlb_mm(oldmm);

这样父进程下一次写入该地址时不能继续使用过期 writable TLB entry，必须进入 page-fault处理。

namespace 为什么没有新建
------------------------

``copy_namespaces(flags=0, p)`` 看到没有任何 ``CLONE_NEW*`` flag，增加现有 ``nsproxy`` 的引用并返回。

所以 parent与 child处于相同的：

* mount namespace；
* PID namespace；
* network namespace；
* IPC、UTS、cgroup和 time namespaces。

“新进程”不自动意味着“新 namespace”。容器隔离需要显式的 clone/unshare flags。

``copy_thread`` 怎样准备 child 的第一次内核返回
----------------------------------------------

x86 ``copy_thread()`` 在 child kernel stack顶部建立 ``fork_frame`` 与 ``pt_regs``：

.. code-block:: c

   *childregs = *current_pt_regs();
   childregs->ax = 0;

普通 fork没有新 userspace stack参数，所以 child继承同一个用户虚拟 ``RSP`` 数值；因为 parent与 child已有不同 mm，它们的栈页遵循相同 COW机制。

函数还设置：

.. code-block:: text

   p->thread.sp       = child fork_frame
   frame->ret_addr    = ret_from_fork_asm
   child FS/GS state  = parent current state
   child FPU state    = cloned architecture state

child并不是从 ``__x64_sys_fork()`` C函数开头再次执行。它第一次被 scheduler选中时，会从 ``ret_from_fork_asm`` 开始恢复这组预先构造的寄存器。

为什么 child 的返回值现在已经是 0
---------------------------------

父进程仍在执行 ``kernel_clone()``，它稍后返回新 PID。child尚未运行，但它的 ``pt_regs->ax`` 已预置为 0。

因此两个返回值并不是同一个寄存器后来被修改两次，而是：

.. code-block:: text

   parent kernel stack pt_regs → 最终写入 child PID
   child  kernel stack pt_regs → copy_thread 已写入 0

两个 task各自保存、恢复自己的 register image。

PID 在什么时候分配
------------------

``copy_thread()`` 成功后，``copy_process()`` 调用：

.. code-block:: c

   pid = alloc_pid(p->nsproxy->pid_ns_for_children, ...);

固定 PID namespace有可用编号。普通 fork没有 ``CLONE_PIDFD``，不分配 pidfd。

内核设置：

.. code-block:: text

   p->pid          = new PID
   p->tgid         = p->pid
   p->group_leader = p
   p->exit_signal  = SIGCHLD
   p->real_parent  = current

child是新的 process/thread-group leader，退出时按普通 fork语义向 parent发送 ``SIGCHLD``。

可见性与可运行性为什么分两步
----------------------------

``copy_process()`` 在 ``tasklist_lock`` 与父 ``sighand->siglock`` 下：

* 建立 PIDTYPE_PID/TGID/PGID/SID links；
* 把 child加入 parent的 children list；
* 把 child加入全局 task list；
* 更新 process/thread counters；
* 完成 cgroup、scheduler、perf与 trace post-fork hooks。

锁释放后，其他内核路径可以通过 PID与 task list发现 child。但 child仍是：

.. code-block:: text

   TASK_NEW
   on_rq = 0

所以“已经全局可见”不等于“已经可以运行”。

当前精确边界
------------

``copy_process()`` 已返回 ``p``，``kernel_clone()`` 接下来取得 child PID并调用：

.. code-block:: c

   wake_up_new_task(p);

当前状态：

* 当前执行者：parent；
* CPU mode：CPL 0，fork syscall context；
* parent mm与 child mm：不同对象；
* parent与 child页表根：不同；
* 固定 anonymous folio：物理页共享；
* parent/child PTE：都只读，等待未来 COW fault；
* files_struct：不同，fd entries引用相同 ``struct file``；
* fs_struct：不同；
* sighand_struct：不同，actions内容复制；
* signal_struct：不同；
* cred object：不同；
* nsproxy：同一对象的引用继承；
* child PID：已分配并发布；
* child parent关系：已建立；
* child user ``RAX`` image：0；
* child first kernel return address：``ret_from_fork_asm``；
* child state：``TASK_NEW``；
* child ``on_rq``：0；
* parent fork返回值：尚未从 ``kernel_clone()`` 返回；
* child：尚未执行任何指令。

关键边界
--------

#. files_struct独立不等于 struct file独立；共享 open file description仍可共享 file offset。
#. fs、sighand、signal和 mm是不同资源对象，普通 fork分别创建新对象。
#. 新 mm与新页表根已经建立，但普通 private data page主要通过 COW共享。
#. COW建立会 write-protect父 PTE和 child PTE。
#. 页表复制不等于立即复制所有物理数据页。
#. child ``RAX=0`` 在 ``copy_thread()`` 中预置，不需要 child重新执行 fork C函数。
#. task publication与 scheduler enqueue是两个独立阶段。

资料
----

* `Linux 7.2-rc1 kernel/fork.c：copy_files、copy_fs、copy_sighand、copy_signal、copy_mm、copy_thread与 PID publication <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/fork.c>`_
* `Linux 7.2-rc1 mm/mmap.c：dup_mmap 与 VMA duplication <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/mmap.c>`_
* `Linux 7.2-rc1 mm/memory.c：copy_page_range、copy_present_ptes与 COW write-protection <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/memory.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/process.c：x86 copy_thread <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/process.c>`_
* `Linux 7.2-rc1 kernel/nsproxy.c：copy_namespaces <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/nsproxy.c>`_
