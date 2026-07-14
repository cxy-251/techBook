第九十九章：begin_new_exec() 怎样替换旧 mm 并建立静态 ELF 映射？
============================================================================

第九十八章结束时，ELF header与program headers已经验证完成，``load_elf_binary()`` 即将调用：

.. code-block:: c

   begin_new_exec(bprm);

本章追踪不可回退阶段：当前child保留task/PID，切换到 ``bprm->mm``，释放旧COW地址空间，执行close-on-exec和signal/credential重置，然后为static ``ET_EXEC`` 建立 ``PT_LOAD`` VMAs与最终用户栈。

``point_of_no_return`` 改变了什么
--------------------------------

``begin_new_exec()`` 在完成最终credential检查后设置：

.. code-block:: c

   bprm->point_of_no_return = true;

这不是一个普通状态标签。后续 ``exec_mmap()`` 会使旧程序映像不可恢复；若之后发生不可处理错误，``bprm_execve()`` 会确保task收到fatal signal，而不是返回旧程序继续执行。

固定child是单线程，因此 ``de_thread(current)`` 不需要杀死同thread-group中的其他线程，也不发生leader PID交换。child的：

.. code-block:: text

   task_struct
   PID / TGID
   parent relationship
   scheduler entity

都继续保留。

``exec_mmap`` 怎样切换 address space
-----------------------------------

在切换前：

.. code-block:: text

   current->mm = old child mm
   bprm->mm    = new exec mm

``exec_mmap(bprm)`` 取得 ``exec_update_lock``，然后在task lock与必要的IRQ保护下执行核心替换：

.. code-block:: c

   current->active_mm = bprm->mm;
   current->mm        = bprm->mm;
   activate_mm(old_mm, bprm->mm);

``activate_mm()`` 为当前CPU加载新address-space context；x86在PTI启用时也会建立后续kernel/user CR3切换所需状态。

旧mm暂时记录在：

.. code-block:: c

   bprm->old_mm = old_mm;

它不会在持有exec关键锁时立即完整teardown。稍后的 ``setup_new_exec()`` 调用 ``exec_mm_put_old()``，再通过 ``mmput(old_mm)`` 释放旧VMAs、page tables和旧child mapping references。

这会移除child旧地址A到COW new folio的映射。parent的mm是另一个独立对象，仍保留它到old folio的只读映射，完全不受本次exec影响。

close-on-exec 在哪里发生
------------------------

``begin_new_exec()`` 确保files table不与其他task共享后调用：

.. code-block:: c

   do_close_on_exec(current->files);

固定fd 5带 ``FD_CLOEXEC``，因此：

.. code-block:: text

   fd 5 entry removed
   → referenced struct file count decremented
   → final reference时执行 file release

没有 ``FD_CLOEXEC`` 的fd继续存在。exec不默认关闭全部文件描述符，也不创建新的 ``files_struct``；它在当前task的独立file table中处理close-on-exec bitmap。

signal 与 thread architecture 状态怎样重置
------------------------------------------

``begin_new_exec()`` 与其后续setup执行：

.. code-block:: text

   flush_thread
   → 清理旧程序的architecture thread state
   do_close_on_exec
   → reset alternate signal stack
   flush_signal_handlers
   → 重置被捕获的signal handlers

显式被忽略的signals按exec语义继续保持ignored；用户安装的caught handlers重置为default。pending signals不会因为exec自动全部消失，但固定场景没有pending signal。

credential为什么仍要提交
------------------------

固定ELF没有setuid、setgid或file capabilities，所以有效uid/gid/capability集合没有特权变化。内核仍执行：

.. code-block:: text

   security_bprm_committing_creds
   → commit_creds(bprm->cred)
   → security_bprm_committed_creds

提交的是经过exec安全流程重新计算的credential对象。无提权不等于跳过credential transaction。

``setup_new_exec`` 什么时候释放旧mm
----------------------------------

回到 ``load_elf_binary()`` 后，kernel设置personality与randomization flags，再调用：

.. code-block:: c

   setup_new_exec(bprm);

它建立新mm的mmap布局与architecture exec状态，释放exec locks，然后：

.. code-block:: c

   exec_mm_put_old(bprm->old_mm);

此后旧child mm不可再访问：

.. code-block:: text

   old anonymous VMAs removed
   old child page tables freed
   child COW new folio mapping removed
   old mm reference released

当前task的PID没有变化，但 ``/proc/<pid>/maps`` 所描述的address space已经变成新exec mm。

argument stack怎样变成正式stack VMA
-----------------------------------

``setup_arg_pages()`` 把temporary stack VMA移动到随机化后的 ``STACK_TOP`` 附近，设置最终stack flags和protection，并保证已复制的：

.. code-block:: text

   "/bin/static-demo"
   "cow-complete"
   "LANG=C"
   "PATH=/bin"

继续位于new mm中。

稍后 ``create_elf_tables()`` 会在这些字符串之前构造ABI要求的pointer table与auxiliary vector；本章先建立承载它们的正式stack VMA。

static ``ET_EXEC`` 的 ``PT_LOAD`` 怎样变成VMA
---------------------------------------------

``load_elf_binary()`` 遍历program headers。每个 ``PT_LOAD`` 根据 ``p_flags`` 生成：

.. code-block:: text

   PF_R → PROT_READ
   PF_W → PROT_WRITE
   PF_X → PROT_EXEC

固定non-PIE ``ET_EXEC`` 的第一个segment使用：

.. code-block:: text

   MAP_PRIVATE | MAP_FIXED_NOREPLACE

后续segment使用：

.. code-block:: text

   MAP_PRIVATE | MAP_FIXED

每次 ``elf_load()`` 最终通过mmap建立以executable file为backing的VMA。普通ext4文件由 ``ext4_file_mmap_prepare()`` 安装：

.. code-block:: c

   vma->vm_ops = &ext4_file_vm_ops;

其中：

.. code-block:: c

   .fault = filemap_fault
   .map_pages = filemap_map_pages

这里建立的是VMA和file offset关系，不是把全部segment复制到anonymous memory，也不保证任何用户PTE已经present。

为什么static ``ET_EXEC`` 没有load bias
-------------------------------------

固定ELF是non-PIE ``ET_EXEC``，所以segment按link-time virtual addresses映射。没有 ``PT_INTERP``，因此：

.. code-block:: text

   load_bias       = 0
   interp_load_addr= 0
   elf_entry       = elf_ex->e_entry

动态链接ELF会把initial userspace entry指向interpreter；当前static路径直接指向program自己的entry。

BSS 与 brk 建立了什么
---------------------

``PT_LOAD`` 中 ``p_memsz > p_filesz`` 的尾部表示zero-initialized区域。kernel处理最后partial page并为超出file内容的BSS范围建立anonymous zero mappings。

随后记录：

.. code-block:: text

   mm->start_code / end_code
   mm->start_data / end_data
   mm->start_brk / brk

这描述新程序的代码、数据和初始heap边界。它们与旧child COW VMA没有继承关系。

最终用户栈包含什么
------------------

``create_elf_tables()`` 在new stack中构造：

.. code-block:: text

   argc = 2
   argv[0] → "/bin/static-demo"
   argv[1] → "cow-complete"
   argv[2] = NULL
   envp[0] → "LANG=C"
   envp[1] → "PATH=/bin"
   envp[2] = NULL
   auxv[]

auxv包含例如program-header地址、entry、page size、uid/gid、random bytes与vDSO相关信息。static ELF没有dynamic interpreter，但仍需要auxv。

当前精确边界
------------

``load_elf_binary()`` 已完成：

.. code-block:: text

   begin_new_exec
   → exec_mmap
   → current->mm = new mm
   → close fd 5
   → reset thread/signal state
   → commit non-privileged creds
   → release old child mm
   → setup_arg_pages
   → map all PT_LOAD VMAs
   → establish BSS/brk
   → create_elf_tables

当前状态：

* current task/PID：仍是原fork child；
* CPU mode：CPL 0，exec syscall context；
* ``current->mm``：new exec mm；
* old child mm：已释放；
* parent mm：不变；
* fd 5：已close-on-exec关闭；
* 其他非-CLOEXEC fd：保留；
* caught signal handlers：已reset；
* credentials：已提交，无uid/gid/capability提升；
* executable VMAs：已按 ``PT_LOAD`` 建立；
* entry text PTE：仍不存在；
* entry text folio：在page cache中；
* user stack：argc/argv/envp/auxv已经构造；
* next entry：``finalize_exec()`` 与 ``START_THREAD``；
* old userspace ``execve`` call site：不会再次执行。

关键边界
--------

#. exec替换mm，不替换task/PID。
#. ``exec_mmap`` 先切换current->mm，旧mm随后在锁外释放。
#. child旧COW映射被销毁，不影响parent独立mm。
#. close-on-exec只关闭带 ``FD_CLOEXEC`` 的entries。
#. no-setuid exec仍走credential commit。
#. ``PT_LOAD`` mmap建立VMA，不会预先填充全部PTE。
#. static ET_EXEC的entry来自自身 ``e_entry``，不是动态解释器。

资料
----

* `Linux 7.2-rc1 fs/exec.c：begin_new_exec、exec_mmap、setup_new_exec 与 do_close_on_exec <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/exec.c>`_
* `Linux 7.2-rc1 fs/binfmt_elf.c：PT_LOAD mapping、setup_arg_pages 与 create_elf_tables <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/binfmt_elf.c>`_
* `Linux 7.2-rc1 fs/ext4/file.c：ext4_file_vm_ops 与 filemap_fault <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/file.c>`_
