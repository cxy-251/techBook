========================================================================================
第 6 节：smpboot.c 与 secondary_startup_64：从核微码加载、独立页表挂载与 CPU 热插拔
========================================================================================

.. note::
   **前置背景与上下文承接**
   * **体系结构基准**：承接模块 08 第 5 节中关于 BSP 引导核选主仲裁、Local APIC 中断命令寄存器（ICR）位域编码、INIT-SIPI-SIPI 两次启动硬件总线时钟时序、1MB 跳板物理地址折算（$	ext{Address} = 	ext{Vector} 	imes 4096$）以及从核在 ``trampoline_64.S`` 中的四级火箭长模式跃迁。
   * **核心使命**：解构从核（AP）在冲破实模式跳板后，如何正式接入未压缩内核汇编入口——``arch/x86/kernel/head_64.S:secondary_startup_64``；深入剖析从核切换脱离跳板页表并挂载内核正式母表 ``init_top_pgt``（``CR3`` 切换）的微观物理过程；逐行推导并行启动模式下读取 APIC ID（``STARTUP_READ_APICID``）反查 CPU 逻辑编号、分配专属 0 号空闲栈（``TASK_threadsp(current_task)``）、释放跳板锁（``trampoline_lock``）、加载独立 GDT/IDT 与设置 ``MSR_GS_BASE`` 的汇编流水线；深度解构 ``arch/x86/kernel/smpboot.c:start_secondary()``、从核 CPU 微码热加载（``load_ucode_ap``）、TSC 时钟跨核硬件对齐同步（``check_tsc_sync_target``）、CPU 热插拔（CPU Hotplug）通用状态机（``cpuhp_step`` / ``CPUHP_BRINGUP_CPU`` / ``CPUHP_AP_ONLINE_IDLE``）以及从核最终步入 ``cpu_startup_entry()`` 蜕变为专属 Idle 线程的全景微观世界，圆满收官模块 08。

----------------------------------------------------------------------------------------

第一幕：从核汇编总入口——``secondary_startup_64`` 物理脱胎换骨
--------------------------------------------------------------

当从属应用处理器（AP）在 1MB 以下的跳板内存（``trampoline_64.S``）中完成 16 位实模式 $\rightarrow$ 32 位保护模式 $\rightarrow$ 64 位兼容模式的快速推进后，指令流执行一条绝对长跳转指令，正式跨入未压缩内核的从核总入口 **``arch/x86/kernel/head_64.S:secondary_startup_64``**：

::

   +-----------------------------------------------------------------------------------+
   |                   secondary_startup_64 从核汇编初始化流水线                       |
   |                                                                                   |
   |  [1. 寄存器清洗与环境校准]                                                        |
   |  - xorl %r15d, %r15d: 清零 R15 (从核不接收 boot_params 零页参数)                  |
   |  - call verify_cpu: 校验本核心 64 位长模式与 NX 硬件特性支持                      |
   |            │                                                                      |
   |            ▼ 2. 挂载正式内核母表 (CR3 物理切换)                                    |
   |  - 计算 init_top_pgt 真实物理基地址 (叠加密钥掩码 sme_me_mask)                     |
   |  - movq %rax, %cr3 ──► 瞬间剥离低端跳板页表，正式挂载全局 init_top_pgt!           |
   |            │                                                                      |
   |            ▼ 3. 识别 CPU 逻辑编号并提取 Per-CPU 偏移量 (common_startup_64)         |
   |  - 从 Local APIC 读取硬件 APIC ID -> 反查 cpuid_to_apicid[] 匹配逻辑 CPU 编号 RCX  |
   |  - movq __per_cpu_offset(,%rcx,8), %rdx: 获取本核心专属 Per-CPU 内存基地址        |
   |            │                                                                      |
   |            ▼ 4. 挂载从核专属 0 号线程栈与释放跳板互斥锁                           |
   |  - 从 current_task(RDX) 提取栈顶指针: movq TASK_threadsp(%rax), %rsp              |
   |  - movl $0, (trampoline_lock): 释放全局跳板锁，允许下一个从核进入跳板             |
   |            │                                                                      |
   |            ▼ 5. 专属架构控制寄存器与中断门绑定                                    |
   |  - lgdt gdt_page(%rdx): 加载本核心专属 GDT 描述符表                               |
   |  - wrmsr MSR_GS_BASE: 将 Per-CPU 基地址写入 GS 寄存器                            |
   |  - call early_setup_idt: 挂载中断描述符表                                         |
   |  - wrmsr MSR_EFER: 使能系统调用 (SCE) 与不可执行保护 (NX)                         |
   |            │                                                                      |
   |            ▼ 6. 跨入 C 语言从核初始化总控                                         |
   |  - callq *initial_code(%rip) ──► 命中 arch/x86/kernel/smpboot.c:start_secondary() |
   +-----------------------------------------------------------------------------------+

1.1 挂载正式内核顶级页表（``init_top_pgt``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在跳板阶段，从核使用的是 1MB 低端内存中的临时跳板页表（Trampoline Page Table）。进入 ``secondary_startup_64`` 后，第一项核心任务是切换至内核正式母表：

::

   /* 1. 根据 phys_base 动态推导 init_top_pgt 在当前运行期的物理基地址 */
   movq    phys_base(%rip), %rax
   addq    $(init_top_pgt - __START_KERNEL_map), %rax

   /* 2. 若 AMD SME 内存加密激活，叠加加密掩码 */
   #ifdef CONFIG_AMD_MEM_ENCRYPT
   addq    sme_me_mask(%rip), %rax
   #endif

   /* 3. 将正式顶级页表物理基地址载入 CR3 */
   movq    %rax, %cr3

.. important::
   **从核 CR3 切换的物理意义**：
   * 指令 ``movq %rax, %cr3`` 执行的瞬间，从核彻底废弃了低端跳板中的临时恒等映射页表；
   * 从核正式接入与引导核（BSP）完全相同的 64 位全局高位虚拟内存体系（``init_top_pgt``），并立即冲刷本地 TLB 缓存，消除了低端跳板内存的任何潜在冲突。

----------------------------------------------------------------------------------------

第二幕：并发启动与从核逻辑编号动态绑定（``common_startup_64``）
----------------------------------------------------------------

在多达数十乃至数百核的现代服务器上，SMP 启动机制经历了从“串行唤醒”向“大规模并发唤醒”的技术演进。

2.1 传统串行启动 vs 现代 Linux 并行启动（Parallel Boot）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **传统串行启动**：BSP 唤醒 AP 1 $\rightarrow$ 等待 AP 1 完全上线 $\rightarrow$ BSP 唤醒 AP 2 $\rightarrow$ 等待 AP 2……百核服务器开机在跳板阶段需耗费数秒；
* **现代并行启动（Parallel Bringup）**：BSP 广播 IPI 信号批量唤醒全部从核，数十个从核并发冲入 ``secondary_startup_64``。

2.2 APIC ID 硬件嗅探与 CPU 逻辑编号反查
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在并行启动模式下，从核必须在没有任何栈和上下文的前提下，通过底层硬件直接获知自己的“身份”：

::

   .Lread_apicid:
       /* 1. 探测是否处于现代 x2APIC 模式 */
       movl    $MSR_IA32_APICBASE, %ecx
       rdmsr
       testl   $X2APIC_ENABLE, %eax
       jnz     .Lread_apicid_msr

   .Lread_apicid_mmio:
       /* 2. 传统 xAPIC: 从 Fixmap 固定映射的 MMIO 空间读取 APIC ID */
       movq    apic_mmio_base(%rip), %rcx
       addq    $APIC_ID, %rcx
       movl    (%rcx), %eax
       shr     $24, %eax               /* EAX 提取出 8 位硬件 APIC ID */
       jmp     .Llookup_AP

   .Lread_apicid_msr:
       /* 3. 现代 x2APIC: 直接通过 MSR 0x802 读取 32 位硬件 APIC ID */
       movl    $APIC_X2APIC_ID_MSR, %ecx
       rdmsr                           /* EAX 返回 32 位全局唯一 APIC ID */

   .Llookup_AP:
       /* 4. 遍历全局映射表 cpuid_to_apicid[]，匹配本核心的逻辑 CPU 编号 (RCX) */
       xorl    %ecx, %ecx
       leaq    cpuid_to_apicid(%rip), %rbx
   .Lfind_cpunr:
       cmpl    (%rbx,%rcx,4), %eax
       jz      .Lsetup_cpu             /* 匹配成功！RCX 中即为当前核心的逻辑 CPU 编号 */
       inc     %ecx
       cmpl    nr_cpu_ids(%rip), %ecx
       jb      .Lfind_cpunr

2.3 挂载从核专属 0 号内核栈与释放跳板互斥锁
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
获取到逻辑编号 ``%rcx`` 后，从核定位到 BSP 为其预先初始化的 Per-CPU 区域：
1. **提取专属内核栈**：
   ::

      movq    __per_cpu_offset(,%rcx,8), %rdx       /* RDX = 本核心专属 Per-CPU 偏移量 */
      movq    current_task(%rdx), %rax              /* RAX = BSP 预先创建的 Idle 进程描述符 */
      movq    TASK_threadsp(%rax), %rsp             /* RSP 载入 0 号进程 16KB 内核栈顶! */

2. **释放跳板互斥锁**：
   ::

      movq    trampoline_lock(%rip), %rax
      movl    $0, (%rax)                            /* 将锁归零，允许下一个排队的从核进入跳板! */

3. **绑定独立 GDT 与 GSBASE**：
   ::

      lgdt    gdt_page(%rdx)                        /* 加载专属 GDT 描述符表 */
      movl    $MSR_GS_BASE, %ecx
      movl    %edx, %eax
      shrq    $32, %rdx
      wrmsr                                         /* 将 Per-CPU 基地址固化写入 GSBASE */

----------------------------------------------------------------------------------------

第三幕：从核 C 语言运行时建制——``start_secondary()``
----------------------------------------------------

从核汇编收尾后，执行 ``callq *initial_code(%rip)``，正式进入 C 语言环境 **``arch/x86/kernel/smpboot.c:start_secondary()``**：

::

   +-----------------------------------------------------------------------------------+
   |                         start_secondary() C 语言初始化流水线                      |
   |                                                                                   |
   |  1. cr4_init_shadow(): 初始化从核片上 CR4 内存影子变量                            |
   |                                                                                   |
   |  2. cpu_init():                                                                   |
   |     - 加载任务状态段 (TSS, Task State Segment) 描述符至 TR 寄存器 (ltr 指令);     |
   |     - 挂载 IST (Interrupt Stack Table) 7 组独立硬件异常物理栈;                    |
   |     - 初始化 FPU / AVX / AVX-512 浮点寄存器扩展上下文状态 (xsave / xcr0);         |
   |                                                                                   |
   |  3. load_ucode_ap():                                                              |
   |     - 向 MSR 0x79 写入补丁基址，完成从核 CPU 微码热加载，与 BSP 保持绝对版本对齐; |
   |                                                                                   |
   |  4. smp_callin() 握手确认:                                                        |
   |     - 执行 check_tsc_sync_target() 完成与 BSP 之间的 TSC 纳秒级跨核时钟同步;      |
   |     - 将本核心位写入 cpu_callin_map 掩码，正式向 BSP 宣告从核存活!               |
   |                                                                                   |
   |  5. 接入 CPU 热插拔状态机:                                                        |
   |     - cpuhp_online_idle(CPUHP_AP_ONLINE_IDLE): 激活调度器运行队列与时钟事件中断;  |
   |                                                                                   |
   |  6. 步入终极空闲循环:                                                             |
   |     - cpu_startup_entry(CPU_HP_ONLINE): 开启本地中断 (IF=1)，进入 do_idle() 循环! |
   +-----------------------------------------------------------------------------------+

----------------------------------------------------------------------------------------

第四幕：跨核硬件时钟对齐与 TSC 纳秒级同步（``check_tsc_sync_target``）
-----------------------------------------------------------------------

在分布式多核芯片上，每个 CPU 核心内部都维护着一个独立的 64 位 TSC（Time Stamp Counter）计数器。

4.1 跨核 TSC 同步的物理必然性
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **时光倒流灾难**：如果 AP 与 BSP 的 TSC 计数器存在数千个时钟周期的偏差，当一个用户进程从 CPU 0 调度迁移至 CPU 1 并调用 ``clock_gettime()`` 时，将观测到时间“回退”，导致数据库事务冲突、分布式锁崩溃与 RCU 宽限期计算紊乱；
* **硬件对齐协议**（``arch/x86/kernel/tsc_sync.c``）：

::

   +-----------------------------------------------------------------------------------+
   |                         TSC 跨核双向同步测量状态机                                |
   |                                                                                   |
   |        [BSP (Master / Source)]                       [AP (Slave / Target)]        |
   |                   │                                             │                 |
   |                   ├─► 1. 写入同步自旋锁 (spin_lock)              │                 |
   |                   ├─► 2. 读取当前基准 TSC (T_bsp_start)          │                 |
   |                   ├─► 3. 释放信号量，通知 AP 采样 ─────────────►│                 |
   |                   │                                             ├─► 4. 采样 T_ap  |
   |                   │◄────────────────────────────────────────────┤                 |
   |                   ├─► 5. 读取完成 TSC (T_bsp_end)                │                 |
   |                   │                                             │                 |
   |                   ▼ 6. 计算跨核时钟相位偏差:                    ▼                 |
   |      Delta = |T_ap - (T_bsp_start + T_bsp_end) / 2|                               |
   |      - 若 Delta < 容差阈值 (如 < 100 周期) ──► 判定 TSC 严格同步 (TSC_SYNC_PASSED)|
   |      - 若多次校准失败 ──► 标记 TSC 不稳定，内核时钟源强制降级为 HPET/ACPI-PM!    |
   +-----------------------------------------------------------------------------------+

----------------------------------------------------------------------------------------

第五幕：CPU 热插拔 (CPU Hotplug) 通用状态机与从核归宿
-----------------------------------------------------

现代 Linux 内核将 CPU 的动态上线（CPU Online）与动态下线（CPU Offline）统一抽象为标准化的 **CPU 热插拔状态机（CPU Hotplug Framework, ``kernel/cpu.c``）**。

5.1 细粒度状态机递进模型
~~~~~~~~~~~~~~~~~~~~~~~~
热插拔框架由数十个按序递增的步骤（``enum cpuhp_state``）构成：

::

   +-----------------------------------------------------------------------------------+
   |                           CPU 上线与下线状态机状态转移                            |
   |                                                                                   |
   |  [CPU 离线状态: CPUHP_OFFLINE]                                                    |
   |        │                                                                          |
   |        ▼ 步骤 1: CPUHP_CREATE_THREADS (BSP 为该 AP 分配专有内核线程与运行队列)    |
   |        ▼ 步骤 2: CPUHP_PERCPU_NOTIFY (通知内存/网络等子系统分配 Per-CPU 资源)    |
   |        ▼ 步骤 3: CPUHP_BRINGUP_CPU (BSP 发送 INIT-SIPI-SIPI 唤醒硬件核心)         |
   |        ▼ 步骤 4: CPUHP_AP_ONLINE_IDLE (AP 启动并在 start_secondary 中执行回调)    |
   |        ▼ 步骤 5: CPUHP_AP_SCHED_STARTING (激活 AP 上的 EEVDF 调度器拓扑)          |
   |        ▼ 步骤 6: CPUHP_AP_IRQ_ONLINE (允许 AP 响应外部硬件中断分发)               |
   |        │                                                                          |
   |        ▼                                                                          |
   |  [CPU 完全在线状态: CPUHP_ONLINE] ──► 从核正式进入通用调度池，全速运行用户负载!   |
   +-----------------------------------------------------------------------------------+

5.2 CPU 动态下电与深睡眠（``play_dead()``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当运维人员执行 ``echo 0 > /sys/devices/system/cpu/cpuX/online`` 将 CPU 动态隔离下线时：
1. **任务与中断全面迁徙**：
   * 调度器将该 CPU 运行队列中的所有任务迁移至其他在线 CPU；
   * ``fixup_irqs()`` 将所有路由至该 CPU 的中断引脚重定向，确保硬件中断不丢失；
2. **硬件关机与深睡眠**：
   * 该 CPU 执行 ``play_dead()`` 汇编代码，刷新本地 L1/L2 缓存并执行 ``cli; wbinvd; mwait;`` 进入超低功耗 C6/C7 睡眠状态，随时等待下一次热插拔唤醒。

5.3 从核终极归宿：``cpu_startup_entry()``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
成功完成全部状态机检查后，从核调用 ``cpu_startup_entry(CPU_HP_ONLINE)``：
* 开启本地中断（``local_irq_enable()``）；
* 从核正式蜕变为全系统中该物理核心专属的 **0 号空闲线程（Idle Thread / ``swapper/X``）**；
* 当该核心运行队列中有就绪任务时，EEVDF 调度器触发上下文切换剥夺 Idle 线程并运行用户程序；当核心空闲时，从核执行 ``mwait/hlt`` 降频节能，实现了算力与能耗的完美平衡！

----------------------------------------------------------------------------------------

第六幕：全模块总结与向模块 09（任务管理与调度器）的历史交接
------------------------------------------------------------

至此，**模块 08：Linux 7.2 中断体系、时钟源与多核 SMP 引导** 全部 6 个核心章节已全量落盘！

我们系统化遍历了 Linux 7.2 操作系统掌控多核硬件与时间维度的全部微观技术奇迹：
1. **中断体系基石**：``trap_init()``、32 向量异常门/陷阱门与 IST 独立硬件异常栈；
2. **中断控制器拓扑**：IO-APIC 物理引脚重定向、Local APIC 与 MSI/MSI-X 消息中断硬件分发；
3. **中断下半部与拓扑**：IRQ Domain 虚拟映射、Softirq 软中断向量与 Workqueue 工作队列；
4. **高精度时钟系统**：HPET / TSC 硬件时钟源、``mult/shift`` 定点数无除法换算与 Tickless (NO_HZ) 动态时钟调度；
5. **SMP 硬件唤醒总线**：BSP 选主仲裁、Local APIC ICR 寄存器位域、INIT-SIPI-SIPI 两次启动时序与 1MB 实模式跳板；
6. **从核建制与热插拔**：``secondary_startup_64`` 汇编初始化、`init_top_pgt` 独立页表挂载、TSC 跨核纳秒级对齐、CPU 热插拔状态机与 Idle 线程诞生。

现在，整机多核计算集群已全部上线：
* 上百个物理 CPU 核心处于完全同步、共享内存与统一中断路由的高效运行状态；
* 每个核心都拥有专属的 0 号空闲任务（Idle Thread）与独立的 Per-CPU 运行队列；
* 硬件时钟高频跳动，中断网全面覆盖。

从下一章开始，我们将正式进入 **模块 09：Linux 7.2 任务管理与 EEVDF 调度器**：

在 **模块 09 第 1 节：``struct task_struct`` 核心拓扑解构：线程描述符、调度实体与内核栈内存布局** 中，我们将深入解构操作系统中最庞大（上千字节）、最核心的元数据结构体——``task_struct``，剖析调度实体（``sched_entity``）、内存描述符（``mm_struct``）、文件描述符表（``files_struct``）与 16KB 内核栈的宏伟拓扑！
