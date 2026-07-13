第七十二章：Linux 怎样选择用户态 init，并把可执行映像装入 PID 1？
=================================================================

第七十一章结束时，内核已经进入 ``SYSTEM_RUNNING``，``__init`` memory 已释放，kernel text/rodata 与 PTI 页表也完成最终收尾。

当前执行者仍是 PID 1，仍在 ``kernel_init()`` 中以 kernel mode 运行。接下来它必须找到一个可执行程序，用新地址空间替换当前启动线程的内核执行上下文。

候选顺序来自 ``kernel_init()``：

.. code-block:: text

   ramdisk_execute_command   默认 /init，或 rdinit=
   → execute_command         init=
   → CONFIG_DEFAULT_INIT
   → /sbin/init
   → /etc/init
   → /bin/init
   → /bin/sh

本章追踪成功候选进入 ``kernel_execve()``、通过 binary-format handler 建立新的用户地址空间，并由 ``START_THREAD()`` 写好用户态寄存器。章节停在 ``kernel_execve()`` 成功返回、``kernel_init()`` 即将返回之前。

到底先尝试 ``/init`` 还是 ``/sbin/init``
-----------------------------------------

第七十章已经完成 root 分支选择：

.. code-block:: text

   initramfs/rootfs 中存在可执行 /init
   → ramdisk_execute_command 保持为 /init

   /init 不可执行
   → ramdisk_execute_command = NULL
   → prepare_namespace() 尝试挂载并 pivot 到 root=/dev/sda1

因此当前候选顺序取决于前一阶段结果。

若 early userspace ``/init`` 存在，PID 1 首先执行它。若不存在，已经切换到块设备 root 的内核会跳过该分支，继续考虑 ``init=``、编译期默认值以及传统路径。

固定 GRUB 命令行没有 ``init=`` 或 ``rdinit=``，但固定 initramfs 的具体内容和 kernel ``CONFIG_DEFAULT_INIT`` 没有锁定，正文不能断言最终文件名。

``run_init_process()`` 准备 argv 与 envp
---------------------------------------

每个候选通过：

.. code-block:: c

   run_init_process(init_filename)

执行。函数先令：

.. code-block:: c

   argv_init[0] = init_filename;

启动早期已经把命令行中 ``--`` 后的参数、bootconfig 的 ``init.*`` 参数以及环境变量整理进 ``argv_init``、``envp_init``。最初默认环境至少包括：

.. code-block:: text

   HOME=/
   TERM=linux

随后调用：

.. code-block:: c

   kernel_execve(init_filename, argv_init, envp_init);

``run_init_process()`` 只是内核内部调用者，不是用户程序执行了 ``execve`` syscall。它直接进入同一套 exec core。

候选失败时怎样继续
------------------

``try_to_run_init_process()`` 对传统路径有两类处理：

* ``-ENOENT``：文件不存在，静默尝试下一个路径；
* 其他错误：文件存在但无法执行，输出具体 errno 后继续。

典型错误包括：

.. code-block:: text

   -EACCES   execute permission、mount noexec 或 LSM 拒绝
   -ENOEXEC  没有 binary-format handler 识别
   -ELIBBAD  ELF interpreter 无效
   -ENOMEM   建立 mm、stack 或映射失败
   -ELOOP    script/interpreter rewrite 层数过深

显式 ``init=`` 与自动 fallback 不同。用户明确指定的 ``init=`` 失败时，内核直接 panic，不会悄悄改跑另一个 init。

若所有默认候选都失败，内核最终触发 ``No working init found`` panic。PID 1 不能正常退出；没有 init 也就没有进程回收者和用户空间生命周期管理者。

``kernel_execve()`` 为什么允许 PID 1 调用
---------------------------------------

``kernel_execve()`` 首先检查：

.. code-block:: c

   if (WARN_ON_ONCE(current->flags & PF_KTHREAD))
       return -EINVAL;

PID 1 是由 ``user_mode_thread(kernel_init, ...)`` 创建的特殊 user task。它从内核函数开始执行，但没有 ``PF_KTHREAD``，因此可以通过 exec 转化为用户进程。

PID 2 ``kthreadd`` 则具有 kernel-thread 身份，不能用同一路径把自己变成普通用户进程。

exec 不创建新的 PID
------------------

``kernel_execve()`` 不调用 ``copy_process()``，也不创建新 ``task_struct``。它替换当前 PID 1 的程序映像：

.. code-block:: text

   before exec
   PID 1 task_struct
   → running kernel_init()
   → no userspace mm image yet

   after successful exec preparation
   same PID 1 task_struct
   → new mm
   → new executable mappings
   → new user stack
   → new credentials/exec state

PID、父子关系、cgroup membership 等 task identity 继续保留；地址空间和程序相关状态被替换。

建立 ``linux_binprm`` 与临时新 mm
--------------------------------

``kernel_execve()`` 使用 kernel pointer 版本的 filename、argv、envp，创建 ``linux_binprm``。初始化路径会：

* 打开目标文件并要求 execute access；
* 创建新的 ``mm_struct``；
* 建立临时用户 stack VMA；
* 保存 stack resource limit；
* 记录 filename、interpreter 与 argument position；
* 为新 credential 做准备。

新 mm 此时仍是“候选地址空间”，尚未替换 current 的旧执行状态。这样在 point-of-no-return 之前，错误仍可安全返回并尝试另一个 init。

参数为何从 kernel memory 复制
----------------------------

普通 ``execve`` 的 argv/envp 来自用户指针，使用 ``copy_strings()``。PID 1 当前没有调用用户 syscall，因此 ``kernel_execve()`` 使用：

.. code-block:: text

   count_strings_kernel()
   copy_strings_kernel()

它仍把字符串复制到未来用户 stack 对应的 pages，并执行相同的 ``ARG_MAX``、单字符串长度与 stack limit 检查。

``argv[0]`` 必须存在。``run_init_process()`` 已把候选路径放入 ``argv_init[0]``，所以成功 init 看到的第一个参数与实际尝试路径一致。

``bprm_execve()`` 建立 exec 安全边界
----------------------------------

准备参数后进入：

.. code-block:: text

   bprm_execve()
   → prepare_bprm_creds()
   → check_unsafe_exec()
   → current->in_execve = 1
   → sched_exec()
   → security_bprm_creds_for_exec()
   → exec_binprm()

``prepare_bprm_creds()`` 创建将来提交的新 credential；``check_unsafe_exec()`` 检查 ptrace、共享 fs 和 no-new-privileges 等状态；LSM 可以在多个 hook 上拒绝执行。

``sched_exec()`` 允许 scheduler 在 NUMA/SMP 环境中选择更适合执行新程序的 CPU。它不保证迁移，也不切换用户态。

binary-format handler 怎样识别文件
---------------------------------

``exec_binprm()`` 调用 ``search_binary_handler()``。后者先读取文件开头到 ``bprm->buf``，再遍历已注册的 ``linux_binfmt``：

.. code-block:: text

   binfmt_elf
   binfmt_script
   optional misc/flat/a.out handlers
   ...

每个 handler 返回：

* 成功：映像已接受；
* ``-ENOEXEC``：不认识，继续下一个 handler；
* 其他错误：停止；
* point of no return：旧映像已经不可恢复，不再尝试其他 handler。

init 文件可能是脚本
-------------------

若目标以 ``#!`` 开头，``binfmt_script`` 读取 interpreter 路径，重写 ``bprm``，再让 exec core 处理解释器。

例如：

.. code-block:: text

   /init
   #!/bin/sh

实际进入用户态的第一份 ELF 可能是 ``/bin/sh``，而脚本路径和可选 interpreter argument 被重新组织进 argv。

``exec_binprm()`` 限制 interpreter rewrite 深度，防止脚本或 binary handler 形成无限递归。最终仍需要某个 handler 真正建立可运行映像。

ELF handler 先验证什么
----------------------

常见成功路径进入 ``load_elf_binary()``。它首先验证：

* ELF magic；
* ``ET_EXEC`` 或 ``ET_DYN`` 类型；
* x86-64 architecture；
* 文件可 mmap；
* program-header table 可读取；
* segment size、offset 和 virtual-address 不溢出；
* GNU property 与 architecture feature 合法。

若存在 ``PT_INTERP``，还会打开 dynamic linker，验证它的 ELF header 与 program headers。动态 init 的第一条用户指令通常位于 loader entry，而不是主 executable 的 ``main``。

``begin_new_exec()`` 是 point of no return
-----------------------------------------

格式和 interpreter 的可恢复检查完成后，``load_elf_binary()`` 调用：

.. code-block:: c

   begin_new_exec(bprm);

此处开始把 candidate mm 提交给 current，并清除旧程序状态。它涉及：

* 处理同 thread group 的其他线程；
* 关闭 close-on-exec file descriptors；
* 更新 executable file；
* 重置信号处理、alt stack 和 personality 相关状态；
* 提交新 credentials；
* 切换到新的 mm；
* 更新 dumpability 与安全状态。

PID 1 当前通常是单线程，但 exec core 不为它另写一套简化实现。

一旦越过 point of no return，失败不能恢复到 ``kernel_init()`` 的旧映像。exec core 会确保当前 task 收到 fatal signal，而不是返回到已被销毁的执行环境。

映射 ELF ``PT_LOAD`` segments
-----------------------------

``load_elf_binary()`` 为每个 ``PT_LOAD`` 计算权限与地址，并通过 mmap 路径建立映射：

.. code-block:: text

   PF_R             → readable
   PF_R | PF_X      → executable text
   PF_R | PF_W      → writable data
   file bytes       → file-backed mapping
   p_memsz > p_filesz → zero-filled BSS tail

``ET_EXEC`` 通常按链接地址放置；``ET_DYN`` 会结合 ASLR 和 load bias 选择地址。若有 dynamic linker，解释器也被映射到自己的 load bias。

这一步建立的是 virtual mappings。ELF 页通常按需 fault 进入 RAM，并非 exec 时把整个程序逐字节读入物理内存。

建立用户 stack 与 ELF auxiliary vector
--------------------------------------

参数字符串先写入新 stack pages，随后 ``create_elf_tables()`` 组织最终用户 stack：

.. code-block:: text

   argc
   argv[]
   NULL
   envp[]
   NULL
   auxiliary vector
   random bytes / platform data
   argument and environment strings

auxiliary vector 向 libc/loader 传递 program-header 地址、page size、entry point、UID/GID、secure-exec 状态、VDSO 等信息。

若程序有 ``PT_INTERP``，寄存器 entry 指向 dynamic linker；auxv 中仍保留主 executable 的 entry 和 program-header 信息，使 loader 可以完成 relocation 后跳入程序入口。

VDSO 与用户地址空间
------------------

x86 的 ``ARCH_SETUP_ADDITIONAL_PAGES`` 可以把 VDSO/VVAR 映射加入新 mm。第六十一章建立的是内核侧 VDSO time data backing；这里才为具体 PID 1 用户地址空间安装可见映射。

这不表示每个时间调用必定走 VDSO。用户 libc 会根据 auxv、clock 类型和可用实现决定是否回退 syscall。

记录 mm 边界
------------

ELF handler写入：

.. code-block:: text

   mm->start_code / end_code
   mm->start_data / end_data
   mm->start_brk / brk
   mm->start_stack
   mm->binfmt

这些字段随后支撑 ``/proc/PID/maps``、``/proc/PID/stat``、core dump、brk syscall 和权限检查。

``START_THREAD()`` 只修改返回框架
--------------------------------

ELF 映射和用户 stack 完成后：

.. code-block:: c

   regs = current_pt_regs();
   finalize_exec(bprm);
   START_THREAD(elf_ex, regs, elf_entry, bprm->p);

在 x86-64 上最终调用 ``start_thread()``，把 PID 1 的 ``pt_regs`` 改成用户返回框架：

.. code-block:: text

   RIP    = ELF entry 或 dynamic linker entry
   RSP    = 新用户 stack top
   CS     = __USER_CS
   SS     = __USER_DS
   RFLAGS = IF | fixed bit
   DS/ES  = user-compatible state
   FS/GS  = reset for new exec context

此刻 CPU 仍在 kernel mode。内核只是准备好“以后退出内核时要恢复的寄存器”。

``kernel_execve()`` 成功为何会返回 0
-----------------------------------

``load_elf_binary()`` 完成后返回 0，依次回到：

.. code-block:: text

   search_binary_handler()
   → exec_binprm()
   → bprm_execve()
   → kernel_execve()
   → run_init_process()
   → kernel_init()

成功并不意味着恢复旧的 ``kernel_init()`` 地址空间。内核栈与 C 调用链仍暂时存在，current 的 mm 和 ``pt_regs`` 已经变成新用户程序的状态。

``kernel_init()`` 看到返回值 0 后立即 ``return 0``。真正的 privilege-level transition 发生在创建 PID 1 时预设的 ``ret_from_fork`` 返回链中，留给下一章。

本章结束时的机器状态
--------------------

本章结束时：

* 当前执行者：PID 1，仍在 kernel mode；
* selected init：由 ``/init``、``init=``、编译期默认值和 fallback 的实际成功项决定；
* task identity：仍是同一个 PID 1，没有 fork 新进程；
* new mm：已提交；
* executable/interpreter：成功 handler 已映射；
* argv/envp/auxv：已放入用户 stack；
* user ``RIP``/``RSP``：已写入 ``pt_regs``；
* user segment selectors 与 ``RFLAGS.IF``：已准备；
* CPU privilege level：仍为 Ring 0；
* precise next step：``kernel_init()`` 返回到 ``ret_from_fork()``。

只有架构退出路径执行 ``swapgs``、可选 user CR3 切换并恢复 IRET frame 后，PID 1 才真正开始执行用户映像。

资料
----

* `Linux 7.2-rc1 init/main.c：init candidate 顺序与 run_init_process <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 7.2-rc1 fs/exec.c：kernel_execve、bprm_execve 与 binary-format dispatch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/exec.c>`_
* `Linux 7.2-rc1 fs/binfmt_elf.c：load_elf_binary、ELF mappings、stack 与 START_THREAD <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/binfmt_elf.c>`_
* `Linux 7.2-rc1 fs/binfmt_script.c：#! interpreter rewrite <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/binfmt_script.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/process_64.c：start_thread_common 与 user register frame <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/process_64.c>`_