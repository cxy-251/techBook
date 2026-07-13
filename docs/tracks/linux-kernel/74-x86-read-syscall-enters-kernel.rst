第七十四章：x86-64 的 read() 怎样从用户态进入 __x64_sys_read？
============================================================

第七十三章结束时，Linux 启动主线已经完成。系统进入 ``SYSTEM_RUNNING``，用户进程通过 syscall、exception 和 interrupt 按需重新进入内核。

从本章开始，正文固定一个新的运行期场景：

.. code-block:: c

   char buf[4096];
   ssize_t n = read(fd, buf, 4096);

为避免把运行时分支混在一起，本阶段固定以下条件：

* CPU 使用 x86-64 native syscall ABI；
* 使用传统 ``SYSCALL`` / ``entry_SYSCALL_64`` 入口，不展开 FRED syscall entry；
* ``fd`` 已经指向 ext4 上的普通文件；
* 文件以 buffered I/O 打开，没有 ``O_DIRECT``，inode 不是 DAX；
* 用户 buffer 已映射并允许写入；
* 从当前 ``f_pos`` 读取 4096 字节；
* 第七十六章再固定 page cache cold miss，当前两章先追踪公共入口。

本章只追踪从用户 ``SYSCALL`` 到 ``__x64_sys_read()``。此时还没有查 fd，也没有访问 page cache。

用户寄存器怎样表达 read(fd, buf, 4096)
---------------------------------------

x86-64 syscall ABI 使用：

.. code-block:: text

   RAX = syscall number
   RDI = argument 0
   RSI = argument 1
   RDX = argument 2
   R10 = argument 3
   R8  = argument 4
   R9  = argument 5

``syscall_64.tbl`` 把 native ``read`` 编号固定为 0。因此执行 ``SYSCALL`` 前，关键寄存器是：

.. code-block:: text

   RAX = 0
   RDI = fd
   RSI = buf
   RDX = 4096

这里描述的是 kernel ABI。用户程序可能通过 glibc、musl 或其他 runtime wrapper 发起调用；wrapper 的实现不改变 Linux 接收到的寄存器约定。

``SYSCALL`` 不会替 Linux 自动建立完整内核栈
------------------------------------------

执行 ``SYSCALL`` 后，CPU 根据预先配置的 x86 syscall MSR 进入 CPL 0，并把用户返回地址与 flags 保存在 ``RCX``、``R11``。x86-64 的 ``SYSCALL`` 不像 privilege-changing ``INT``/``IRET`` frame 那样自动切换到内核 task stack。

因此 ``entry_SYSCALL_64`` 必须立即完成 Linux 自己的入口工作：

.. code-block:: text

   swapgs
   → save user RSP in per-CPU TSS scratch slot
   → optional SWITCH_TO_KERNEL_CR3
   → load current task kernel-stack top into RSP

``swapgs`` 把 GS base 切到 kernel per-CPU 区域，之后汇编才能通过 ``PER_CPU_VAR`` 访问当前 CPU 的 TSS、task stack 与 entry state。

如果 PTI 已启用，``SWITCH_TO_KERNEL_CR3`` 从受限的 user page table 切到完整 kernel page table；未启用时该路径退化为不切换 CR3。无论 PTI 是否开启，内核栈切换都必须完成。

入口汇编怎样建立 ``struct pt_regs``
----------------------------------

切到当前 task 的 kernel stack 后，``entry_SYSCALL_64`` 依次保存：

.. code-block:: text

   SS
   user RSP
   RFLAGS
   CS
   user RIP
   orig_ax
   general-purpose registers

这些内容形成当前 task stack 顶部的 ``struct pt_regs``。其中：

* ``orig_ax`` 保存原始 syscall number 0；
* ``di``、``si``、``dx`` 保存 ``fd``、``buf``、``4096``；
* ``ip``、``sp``、``cs``、``ss``、``flags`` 保存未来返回用户态所需的 frame；
* ``ax`` 暂时被初始化为 ``-ENOSYS``，只有合法 syscall 完成分派后才覆盖。

因此进入 C 代码时，用户寄存器不再依赖仍处于硬件寄存器中的瞬时状态，而是被固化到可检查、可追踪、可被 signal/ptrace 修改的 ``pt_regs`` 中。

为什么在调用 C 代码前保持 IRQ disabled
-------------------------------------

``entry_SYSCALL_64`` 注明调用 ``do_syscall_64()`` 时 IRQ 关闭。入口阶段正在切换 GS、CR3、stack 并拼装 register frame；这些中间状态不能被普通 interrupt 当作完整 kernel context 使用。

真正进入通用 entry state 后，``syscall_enter_from_user_mode()`` 才按统一规则处理 context tracking、RCU、lockdep、tracing 和可允许的中断状态。返回前 ``do_syscall_64()`` 又会把状态整理为汇编可以安全退出的形式。

``do_syscall_64()`` 怎样识别 syscall 0
-------------------------------------

入口汇编把两个参数传给 C 函数：

.. code-block:: c

   do_syscall_64(regs, nr);

其中 ``regs`` 指向刚建立的 ``pt_regs``，``nr`` 是 sign-extended ``EAX``，本场景为 0。

``do_syscall_64()`` 的主要顺序是：

.. code-block:: text

   syscall_enter_from_user_mode(regs, nr)
   → instrumentation_begin()
   → add_random_kstack_offset()
   → do_syscall_x64(regs, nr)

``add_random_kstack_offset()`` 在配置启用时改变本次 syscall 的 kernel stack offset，用于降低稳定栈布局带来的攻击价值。它不会改变 ``pt_regs`` 中的用户参数语义。

``do_syscall_x64()`` 先把 syscall number 转成 unsigned 并检查 ``NR_syscalls``，再通过 ``array_index_nospec()`` 限制 speculative index。合法编号进入：

.. code-block:: c

   regs->ax = x64_sys_call(regs, unr);

固定 ``read = 0``，因此 ``x64_sys_call()`` 的 generated switch 选择：

.. code-block:: text

   case 0
   → __x64_sys_read(regs)

当前版本不再依赖传统 ``sys_call_table[nr]`` 做实际分派；``sys_call_table`` 仍保留给 syscall tracing 等代码查询地址，native 调用本身走 generated switch。

``__x64_sys_read`` 为什么只接收一个 ``pt_regs *``
-----------------------------------------------

源码中真正写的是：

.. code-block:: c

   SYSCALL_DEFINE3(read,
       unsigned int, fd,
       char __user *, buf,
       size_t, count)

x86 syscall wrapper 宏会生成 ``__x64_sys_read(const struct pt_regs *regs)``。该 stub 按 native ABI 解码：

.. code-block:: text

   regs->di → fd
   regs->si → buf
   regs->dx → count

随后经过 ``__se_sys_read()`` 做类型和 sign-extension 处理，最终调用实际的 ``__do_sys_read(fd, buf, count)``。编译器通常会内联这些薄 wrapper，但源码语义仍分为“架构寄存器解码”和“通用 syscall 实现”两层。

这样设计有两个直接作用：

* 架构入口只需要传递一份完整 ``pt_regs``；
* 未使用的用户寄存器不会作为随机参数内容继续向内核深层传播。

本章结束时的状态
----------------

本章结束时：

* 当前执行者：发起 ``read()`` 的用户 task；
* CPU mode：CPL 0，运行在该 task 的 kernel stack；
* 当前入口：``__x64_sys_read(regs)``；
* syscall number：0，已完成范围检查与 nospec 限制；
* 参数：已经从 ``pt_regs`` 解码为 ``fd``、``buf``、``4096``；
* fd table：尚未查询；
* ``struct file``：尚未取得；
* VFS permission：尚未检查；
* ext4/page cache/block I/O：尚未进入；
* user return frame：保存在 kernel stack 的 ``pt_regs`` 中。

下一入口是 ``SYSCALL_DEFINE3(read)`` 的函数体调用 ``ksys_read(fd, buf, count)``。下一章从 fd lookup、共享 ``f_pos`` 保护与 ``vfs_read()`` 开始。

资料
----

* `Linux 7.2-rc1 arch/x86/entry/syscalls/syscall_64.tbl：read 的 syscall number <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/syscalls/syscall_64.tbl>`_
* `Linux 7.2-rc1 arch/x86/entry/entry_64.S：entry_SYSCALL_64、pt_regs 与 SYSRET/IRET 返回入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/entry_64.S>`_
* `Linux 7.2-rc1 arch/x86/entry/syscall_64.c：do_syscall_64 与 x64_sys_call switch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/syscall_64.c>`_
* `Linux 7.2-rc1 arch/x86/include/asm/syscall_wrapper.h：x86 syscall wrapper 与寄存器解码 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/syscall_wrapper.h>`_
* `Linux 7.2-rc1 fs/read_write.c：SYSCALL_DEFINE3(read) <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/read_write.c>`_
* `Linux 7.2-rc1 Documentation/core-api/entry.rst：syscall entry/exit 状态模型 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/core-api/entry.rst>`_