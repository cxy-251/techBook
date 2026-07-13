项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-073``。最新三章：

#. ``LK-BOOT-071``：Linux 怎样释放 __init 内存并进入 SYSTEM_RUNNING？
#. ``LK-BOOT-072``：Linux 怎样选择用户态 init，并把可执行映像装入 PID 1？
#. ``LK-BOOT-073``：x86 怎样让 PID 1 从 ret_from_fork 真正进入用户态？

完整章节列表见 ``docs/tracks/linux-kernel/index.rst``，机器可读接续信息见 ``manifests/tracks/linux-kernel.toml``。

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GNU GRUB 2.14 i386-pc
   → bzImage
   → Linux 7.2-rc1
   → PID 1 userspace init entry

固定来源
--------

::

   SeaBIOS commit    = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   QEMU commit       = a759542a2c62f0fd3b65f5a66ad9868201014669
   GNU GRUB release  = 2.14
   GRUB commit       = d38d6a1a9b79427848976f53d474392cd29c2a71
   Linux release     = 7.2-rc1
   Linux repository  = gregkh/linux
   Linux commit      = 7404ce51637231382873d0b55edabc2f3b841a9d

源码版本纠正
------------

固定 Linux commit ``7404ce51637231382873d0b55edabc2f3b841a9d`` 的 ``Makefile`` 标识为 ``7.2-rc1``。旧章节中残留的 ``Linux 6.12.95`` 只是历史显示标签错误；技术事实继续以固定 commit 为权威来源。

当前控制流位置
--------------

第七十一至七十三章已经完成：

::

   PID 1 kernel_init()
   → async_synchronize_full()
   → system_state = SYSTEM_FREEING_INITMEM
   → kprobe_free_init_mem()
   → ftrace_free_init_mem()
   → kgdb_free_init_mem()
   → exit_boot_config()
   → free_initmem()
   → mark_readonly()
   → pti_finalize()
   → system_state = SYSTEM_RUNNING
   → numa_default_policy()
   → rcu_end_inkernel_boot()
   → do_sysctl_args()

   → choose init candidate
   → /init, init=, CONFIG_DEFAULT_INIT,
     /sbin/init, /etc/init, /bin/init, /bin/sh
   → run_init_process()
   → kernel_execve()
   → prepare linux_binprm and new mm
   → copy kernel argv/envp to user stack
   → bprm_execve()
   → search_binary_handler()
   → script rewrite or load_elf_binary()
   → begin_new_exec()
   → map executable/interpreter PT_LOAD segments
   → build argc/argv/envp/auxv stack
   → START_THREAD()
   → write user RIP/RSP/CS/SS/RFLAGS into pt_regs
   → kernel_init() returns 0

   → resume ret_from_fork()
   → regs->ax = 0
   → syscall_exit_to_user_mode()
   → ret_from_fork_asm
   → FRED exit or swapgs_restore_regs_and_return_to_usermode
   → optional PTI trampoline stack and user CR3 switch
   → swapgs
   → iretq
   → PID 1 executes first userspace instruction

此刻机器状态
------------

* system state：``SYSTEM_RUNNING``；
* PID 0：CPU0 的 idle task，其他 online CPU 也有各自 idle task；
* PID 1：已进入用户态 init、dynamic linker 或 script interpreter；
* PID 2：``kthreadd`` 正常运行；
* CPU mode：运行 PID 1 的 CPU 为 x86-64 CPL 3；
* user address space：成功 exec 建立的 mm 已激活；
* user stack：包含 argc、argv、envp 与 auxiliary vector；
* user entry：由实际成功的 init 文件及其 ``PT_INTERP``/``#!`` 决定；
* PTI：启用时已切换到用户 CR3，未启用时沿共享 page table 路径返回；
* interrupts：用户 ``RFLAGS.IF`` 已置位；
* ``__init`` memory：已释放并可复用；
* kernel text/rodata：最终权限已固化；
* boot-only RCU state：已结束；
* kernel boot handoff：完成。

关键边界
--------

必须继续分开：

#. ``SYSTEM_RUNNING`` 表示内核运行阶段完成，不等于 PID 1 已进入用户态；
#. ``START_THREAD()`` 只准备 ``pt_regs``，不切换 CPL；
#. ``kernel_execve()`` 成功不创建新 PID，仍是同一个 PID 1；
#. dynamic ELF 的第一条用户指令通常在 dynamic linker，不是 C ``main``；
#. initramfs 文件名不决定是否存在可执行 ``/init``；
#. ``iretq``/FRED 完成后才真正发生 Ring 0 到 Ring 3 的交接。

当前下一步
----------

启动链已经到达自然终点。固定主线没有锁定 initramfs 内容、最终 init executable 或用户态运行日志，因此不存在一个可诚实断言的“PID 1 第一条 syscall”。

继续写作时先选择明确的运行期场景，再建立新的固定入口。适合的主线包括：

* ``read()``：syscall entry → VFS → filesystem → page cache/block I/O；
* ``openat()``：pathname lookup → dcache → inode permission → file；
* ``fork()``：clone → copy_process → scheduler wakeup；
* page fault：IDT exception → VMA lookup → anonymous/file fault；
* timer interrupt：APIC vector → tick → scheduler；
* block I/O：bio → request queue → AHCI → completion interrupt。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。
