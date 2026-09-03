======================================================
模块 01：CPU 硬件执行与特权控制基石
======================================================

本模块深入计算机体系结构底层，系统化剖析 CPU 物理寄存器构成、时钟时序状态机、执行现场 (Context) 严格物理定义、硬件中断 (IRQ) 仲裁与中断向量表 (IDT/VBAR) 触发机制，以及 CPU 特权级硬件隔离 (Ring 3 vs Ring 0) 与系统调用微观切栈流水线。

.. toctree::
   :maxdepth: 2

   01_registers_and_context
   02_interrupts_and_traps
   03_privilege_and_syscall
