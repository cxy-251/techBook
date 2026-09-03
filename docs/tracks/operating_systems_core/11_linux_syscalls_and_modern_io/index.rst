======================================================================
模块 11：Linux 7.2 现代 I/O 引擎、系统调用与内核基础设施
======================================================================

本模块深入剖析 Linux 7.2-rc1 系统调用与现代高性能异步 I/O 基础设施：`entry_SYSCALL_64` 汇编入口、MSR_LSTAR 硬件跳转与 pt_regs 保存、vDSO (Virtual Dynamic Shared Object) 内存只读映射与用户态免系统调用计时器读取、现代异步 I/O 引擎 `io_uring` 提交队列 (SQ) 与完成队列 (CQ) 共享内存环形缓冲区设计、`epoll` 事件多路复用红黑树与就绪链表回调，以及信号机制 (Signals) 生成、悬挂队列与用户栈帧注入。

.. toctree::
   :maxdepth: 2

   01_syscall_entry_msr_lstar_pt_regs
   02_vdso_vgetcpu_gettimeofday
   03_io_uring_sq_cq_ring_buffers
   04_epoll_rbtree_and_readylist
   05_signals_generation_delivery_sigreturn
