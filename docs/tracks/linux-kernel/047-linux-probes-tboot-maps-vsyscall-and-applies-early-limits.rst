第四十七章：Linux 怎样探测 tboot、映射 vsyscall 并在固件枚举前限制 CPU？
============================================================================

第四十六章结束时，``setup_arch()`` 已经完成 x86-64 paging 收尾，并在配置启用时建立正式 KASAN shadow。当前下一条调用是：

.. code-block:: c

   tboot_probe();

本章追踪到 ``acpi_boot_init()`` 调用前。它处理三个看起来互不相关、实际都必须在完整 SMP/中断拓扑落地前完成的事项：

* 检查本次启动是否来自 Intel TXT/tboot measured launch；
* 为旧 64 位用户空间 ABI 准备固定地址 ``vsyscall`` 页；
* 扫描会影响 APIC、HPET、IOMMU 和 stolen memory 的早期 PCI quirk，并把 ``maxcpus=``、``nosmp``、``nolapic`` 等限制提前施加到 CPU 枚举。

``tboot_probe()`` 在寻找什么
---------------------------

Intel Trusted Execution Technology（TXT）可以由 ``tboot`` 在进入 Linux 前建立 measured launch environment。若存在，bootloader 会通过 x86 boot protocol 在：

.. code-block:: c

   boot_params.tboot_addr

传入一页共享结构的物理地址。

这页数据不是普通命令行参数。Linux 后续关机、S3、DMAR 和可信启动协作可能需要访问：

* tboot UUID 与版本；
* tboot 自身物理基址和大小；
* shutdown entry；
* 日志区；
* MAC region；
* ACPI sleep 协作字段。

固定主线由 GRUB 直接加载普通 Linux bzImage，没有 tboot measured launch，因此 ``boot_params.tboot_addr`` 预期为零。

第一道判断为什么只是地址是否为零
--------------------------------

``tboot_probe()`` 首先执行：

.. code-block:: c

   if (!boot_params.tboot_addr)
       return;

这使普通启动完全绕过后续 fixmap 和结构校验。

若地址非零，Linux 仍不能直接把该值转换成虚拟地址并解引用。boot parameter 可能损坏，也可能由不可信启动环境留下。

为什么必须验证 E820 类型
-----------------------

函数检查 ``tboot_addr`` 所在区域是否被 E820 标记为 ``E820_TYPE_RESERVED``。

其目的不是证明内容一定可信，而是避免把一个落在普通 RAM、MMIO 空洞或不存在地址上的垃圾值映射进 fixmap。

源码中的判断是：

.. code-block:: c

   if (!e820__mapped_any(boot_params.tboot_addr,
                          boot_params.tboot_addr,
                          E820_TYPE_RESERVED))
       return;

只有通过这一层，才执行：

.. code-block:: c

   set_fixmap(FIX_TBOOT_BASE, boot_params.tboot_addr);
   tboot = (void *)fix_to_virt(FIX_TBOOT_BASE);

fixmap 提供一个编译期固定的内核虚拟槽位，把任意指定物理页临时映射到稳定虚拟地址。

为什么还要检查 UUID 和版本
-------------------------

映射成功只说明 CPU 可以访问该物理页，不能说明它真是 tboot shared page。

``check_tboot_version()`` 比较 16 字节 UUID，并要求：

.. code-block:: text

   version >= 5

若 UUID 或版本错误，全局 ``tboot`` 指针重新置为 ``NULL``。后续 ``tboot_enabled()`` 只有在完整验证后才返回真。

当前固定主线在最开始的零地址判断就返回，不创建 ``FIX_TBOOT_BASE`` 映射，也不建立 tboot shutdown trampoline。

为什么 tboot 探测要放在正式 APIC 初始化前
--------------------------------------

tboot 运行时支持不仅影响关机。可信启动环境还可能参与：

* DMA remapping 状态；
* AP shutdown/wait-for-SIPI 流程；
* S3 resume；
* crash 或 reboot 时的可信环境退出。

因此 Linux 必须尽早知道“本次是否在 tboot 下运行”，让后续 IOMMU、ACPI sleep 与 CPU 控制路径选择正确实现。

``map_vsyscall()`` 为什么仍然存在
--------------------------------

下一条调用：

.. code-block:: c

   map_vsyscall();

现代 64 位用户程序通常通过 vDSO 或 ``syscall`` 指令进入内核。``vsyscall`` 是更早期 x86-64 ABI 留下的兼容接口，在固定虚拟地址附近提供：

.. code-block:: text

   gettimeofday
   time
   getcpu

旧二进制可能把这些入口地址直接写死。完全删除该地址会破坏兼容性，因此 Linux 保留可配置模式。

固定地址为什么位于内核高地址范围
-------------------------------

``VSYSCALL_ADDR`` 位于 x86-64 canonical address 的高端区域。它是一个特殊例外：

.. code-block:: text

   内核地址范围中的用户可访问页

普通内核页表上层 entry 通常不设置 ``_PAGE_USER``。若 vsyscall 启用，覆盖该地址的 PGD/P4D/PUD/PMD 都必须允许用户态 page walk 继续向下。

``set_vsyscall_pgtable_user_bits()`` 逐层读取现有 entry，再 OR 上 ``_PAGE_USER``。

三种 vsyscall 模式
------------------

Linux 支持的核心模式包括：

.. code-block:: text

   emulate
   xonly
   none

``emulate`` 模式下，固定地址确实存在一张 PTE。用户态执行旧入口时，内核通过 fault/trap 路径模拟相应系统调用语义。

``xonly`` 模式保持 gate VMA 的执行语义，但不为普通读取提供同样的可见性。

``none`` 模式完全禁用兼容页。

具体默认值由内核配置和 ``vsyscall=`` 命令行决定。本书固定命令行没有指定该参数，所以沿用构建配置默认值，正文不虚构固定模式。

``map_vsyscall()`` 在 emulate 模式做什么
--------------------------------------

它取得链接进内核映像的 ``__vsyscall_page`` 物理地址：

.. code-block:: c

   physaddr_vsyscall = __pa_symbol(&__vsyscall_page);

然后把 fixmap 槽位 ``VSYSCALL_PAGE`` 映射为：

.. code-block:: c

   PAGE_KERNEL_VVAR

并对 ``swapper_pg_dir`` 的上层页表 entry 设置 ``_PAGE_USER``。

函数最后用 ``BUILD_BUG_ON`` 验证 fixmap 计算出的虚拟地址确实等于 ABI 规定的 ``VSYSCALL_ADDR``。这不是运行时容错，而是编译期保证：页表布局一旦改坏固定 ABI，内核直接无法通过构建。

``gate_vma`` 不是真正插入每个 mm 的普通 VMA
-----------------------------------------

vsyscall 定义了一个伪 VMA：

.. code-block:: text

   vm_start = VSYSCALL_ADDR
   vm_end   = VSYSCALL_ADDR + PAGE_SIZE
   name     = [vsyscall]

它让 ptrace、core dump 和地址检查接口能把固定页视作一个可描述区域。它不是通过普通 ``mmap()`` 为每个进程创建的动态映射。

因此这一步也没有创建用户进程。当前系统仍只有 ``init_task``，scheduler 尚未运行。

``x86_32_probe_apic()`` 对当前 x86-64 主线的意义
------------------------------------------------

源码随后保留：

.. code-block:: c

   x86_32_probe_apic();

该入口用于 32 位 x86 选择 APIC driver。当前架构固定为 x86-64，真正的 APIC driver 选择已由 64 位路径和 earlier APIC setup 负责，因此这一调用在当前构建中不承担 32 位 probe 工作。

保留统一调用顺序使 ``setup_arch()`` 不必为每个架构分支复制大段控制流。

``early_quirks()`` 为什么不能等 PCI core
--------------------------------------

下一步：

.. code-block:: c

   early_quirks();

源码开头明确说明：这里的代码运行得太早，不能使用普通 PCI subsystem。

它使用直接 PCI config access，从 bus 0 开始执行一个“简化 PCI 扫描”：

.. code-block:: text

   bus
   → slot 0..31
   → function 0..7
   → vendor/device/class 匹配 early_qrk[]
   → 遇到 PCI bridge 时递归扫描 secondary bus

这不是完整 PCI 枚举。它不创建设备对象、不分配 BAR、不绑定驱动，只为了在 timer、APIC、IOMMU 和普通 PCI 初始化前修正必须立即处理的硬件问题。

早期 quirk 处理哪些类型的问题
----------------------------

表中包括的典型类别有：

* AMD HyperTransport extended APIC interrupt broadcast；
* VIA GART IOMMU 限制；
* NVIDIA/ATI timer override 问题；
* 某些 Intel 芯片组 IRQ remapping 缺陷；
* Intel integrated graphics stolen memory；
* Bay Trail HPET 缺陷；
* 部分 Apple/Broadcom 设备复位。

这些修正可能直接改变后面 ACPI MADT、HPET、IOAPIC 或 IOMMU 的解释，因此不能等对应驱动加载后再处理。

q35 主线是否一定命中 quirk
--------------------------

QEMU q35 暴露 Intel 风格 host bridge、ICH9 southbridge 和可选虚拟显示/PCI 设备。``early_quirks()`` 会扫描它们，但是否命中某条 quirk 取决于 QEMU 具体 device ID 与所附设备。

本书固定主线没有规定 Intel iGPU、Broadcom 网卡或有缺陷实体芯片组，因此不假定某个 invasive quirk 一定执行。

可以确定的是：扫描框架运行，并在完整 ACPI/APIC 初始化前完成所有匹配的早期修正。

为什么现在应用 CPU 命令行上限
---------------------------

接下来：

.. code-block:: c

   topology_apply_cmdline_limits_early();

Linux 在 early MADT pass 中已经看见部分 APIC entry，但完整 ``acpi_boot_init()`` 和 MP table parser 即将继续登记 CPU。

如果用户指定：

.. code-block:: text

   maxcpus=0
   nosmp
   nolapic
   possible_cpus=N

内核必须在固件 parser 继续分配 logical CPU ID 前缩小 ``nr_cpu_ids``。否则会先为大量 CPU 分配拓扑槽位，之后再截断，造成状态不一致和不必要的启动期内存开销。

限制算法
--------

函数从当前 ``nr_cpu_ids`` 开始：

.. code-block:: c

   possible = nr_cpu_ids;

若：

.. code-block:: c

   !setup_max_cpus || apic_is_disabled

则强制：

.. code-block:: c

   possible = 1;

随后与 ``possible_cpus=N`` 对应的 ``max_possible_cpus`` 取最小值。

只有新值小于当前 ``nr_cpu_ids`` 时，才调用：

.. code-block:: c

   set_nr_cpu_ids(possible);

当前固定命令行没有 ``maxcpus=``、``nosmp``、``nolapic`` 或 ``possible_cpus=``，因此正常 q35 SMP 构建保持原始上限。

``possible CPU`` 不等于在线 CPU
-------------------------------

这里限制的是未来能够分配的 logical CPU 编号空间。

当前仍然只有：

.. code-block:: text

   CPU 0 online and executing

MADT 中登记的其他 CPU 只是 topology candidate。它们还没有：

* per-CPU area；
* idle task；
* scheduler runqueue；
* kernel stack；
* INIT/SIPI 启动；
* online bit。

本章结束时为什么停在 ``acpi_boot_init()`` 前
-------------------------------------------

到这里，Linux 已经：

* 确认普通启动没有 tboot shared page，或验证了可信启动结构；
* 根据配置准备 vsyscall 固定 ABI 页；
* 执行所有必须早于完整 PCI/interrupt 初始化的 quirk；
* 在固件完整 CPU 枚举前应用命令行 CPU 上限。

下一条：

.. code-block:: c

   acpi_boot_init();

会从 FADT、MADT、HPET 等表建立完整启动期 ACPI 中断模型，并与 MP table fallback、Local APIC 和 IOAPIC 映射汇合。那是一个新的自然阶段。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* interrupts：关闭；
* tboot：固定主线未检测到 measured launch shared page；
* vsyscall：已按构建配置/命令行完成固定页或兼容模式设置；
* early PCI quirks：已扫描并应用匹配项；
* CPU 命令行上限：已在完整 firmware CPU enumeration 前生效；
* MADT early pass：已完成；
* FADT/HPET/完整 MADT interrupt pass：尚未完成；
* Local APIC/IOAPIC 最终映射：尚未完成；
* AP：尚未唤醒；
* ``setup_arch()``：尚未返回。

下一条控制流是：

.. code-block:: c

   acpi_boot_init();

资料
----

* `Linux 6.12.95 setup.c：tboot、vsyscall、early quirks 与 topology limit 调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c>`_
* `Linux 6.12.95 tboot.c：shared page 映射、UUID 与版本校验 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/tboot.c>`_
* `Linux 6.12.95 vsyscall_64.c：固定地址页、gate VMA 和 USER page-table bits <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/vsyscall/vsyscall_64.c>`_
* `Linux 6.12.95 early-quirks.c：early PCI direct scan 与 quirk table <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/early-quirks.c>`_
* `Linux 6.12.95 topology.c：topology_apply_cmdline_limits_early <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/cpu/topology.c>`_
* `Linux x86 boot protocol：tboot_addr 字段 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/arch/x86/boot.rst>`_