第八章：SeaBIOS 怎样启用 q35 MMCONFIG 并为 PCI 设备分配地址？
==============================================================

上一章结束时，SeaBIOS 已经完成 PCI 总线编号，并把每个已发现 function 的身份和桥接关系保存到
``PCIDevices``。控制流仍在：

::

   qemu_platform_setup()
   → pci_setup()
   → pci_probe_devices() 返回

此时 SeaBIOS 只知道设备“是谁”和“挂在哪里”。设备的 BAR 还没有获得可使用的地址，桥后面的 I/O 与 MMIO
窗口也没有建立。

``pci_setup()`` 接下来执行：

.. code-block:: c

   pcimem_start = RamSize;
   pci_bios_init_platform();

   struct pci_bus *busses = malloc_tmp(
       sizeof(*busses) * (MaxPCIBus + 1));
   if (!busses) {
       warn_noalloc();
       return;
   }
   memset(busses, 0, sizeof(*busses) * (MaxPCIBus + 1));

   if (pci_bios_check_devices(busses))
       return;
   pci_bios_map_devices(busses);

``malloc_tmp()`` 和后续region-entry分配必须成功，才能到达本章出口。 ``busses`` 分配失败时 ``pci_setup()``
警告并返回； ``pci_bios_check_devices()`` 中途失败也直接返回，并不把已经发生的平台配置包装成事务回滚。

本章沿这条控制流继续，直到 ``pci_bios_map_devices()`` 返回：

::

   识别 q35 MCH
   → 启用 PCIEXBAR / MMCONFIG
   → 把 MMCONFIG 区域加入 E820 保留区
   → 测量每个 BAR 的大小和类型
   → 从子总线向父总线汇总桥窗口需求
   → 规划根总线 I/O、32 位 MMIO 和 64 位 MMIO 区域
   → 写入 endpoint BAR
   → 写入 PCI bridge base/limit 窗口

这一步完成后，PCI function 已经拥有地址，但还没有统一完成 INTx 路由、设备专用初始化和 ``PCI_COMMAND``
解码使能。那些动作属于 ``pci_bios_init_devices()``，留到下一段继续。

本章固定使用：

::

   repository: coreboot/seabios
   commit: c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf

为什么先把 pcimem_start 设成 RamSize
-----------------------------------

``pci_probe_devices()`` 返回后，``pci_setup()`` 先执行：

.. code-block:: c

   pcimem_start = RamSize;

``RamSize`` 是 SeaBIOS 前面从QEMU E820或CMOS得到的低于4 GiB的RAM上界记录；在E820路径中，它取已读取
``E820_RAM`` 项的最高末端，源码本身不在这里重新证明0到该值处处连续。把 ``pcimem_start`` 先设为它，表达的是
平台修正前的最低约束：PCI MMIO空间不能直接覆盖已报告的客户机RAM。

但这还不是 q35 的最终 PCI MMIO 起点。不同平台对 4 GiB 以下地址空间有不同的固定窗口和保留区，SeaBIOS
随后会根据已经发现的 host bridge 修正这个值。

默认的 32 位 PCI MMIO 上界来自 ``src/config.h``：

::

   BUILD_PCIMEM_END = 0xfec00000

``0xfec00000`` 是传统 IOAPIC 映射位置，所以普通 PCI BAR 不能继续向上覆盖它。当前待分配的 32 位 MMIO
空间最终必须落在：

::

   pcimem_start <= PCI MMIO < 0xfec00000

具体的 ``pcimem_start`` 将由 q35 host bridge 初始化决定。

pci_bios_init_platform 用设备身份选择平台函数
-------------------------------------------

SeaBIOS 没有因为编译目标叫 QEMU，就直接假设当前一定是 q35。``pci_bios_init_platform()`` 遍历上一章建立的
``PCIDevices``：

.. code-block:: c

   static const struct pci_device_id pci_platform_tbl[] = {
       PCI_DEVICE(PCI_VENDOR_ID_INTEL,
                  PCI_DEVICE_ID_INTEL_82441,
                  i440fx_mem_addr_setup),
       PCI_DEVICE(PCI_VENDOR_ID_INTEL,
                  PCI_DEVICE_ID_INTEL_Q35_MCH,
                  mch_mem_addr_setup),
       PCI_DEVICE_END
   };

   static void
   pci_bios_init_platform(void)
   {
       struct pci_device *pci;
       foreachpci(pci)
           pci_init_device(pci_platform_tbl, pci, NULL);
   }

当前固定平台是 q35，其 host bridge 通常位于 ``00:00.0``，设备 ID 为：

::

   Intel Q35 MCH = 0x29c0

匹配成功后，SeaBIOS 调用：

.. code-block:: c

   mch_mem_addr_setup(dev, NULL);

因此平台类型不是由章节标题决定，而是由 PCI 配置空间中真实读到的 vendor/device ID 决定。

q35 的 PCIEXBAR 建立 256 MiB 配置空间窗口
---------------------------------------

``mch_mem_addr_setup()`` 首先配置 q35 MCH 的 ``PCIEXBAR``。固定值定义为：

::

   Q35_HOST_BRIDGE_PCIEXBAR_ADDR = 0xb0000000
   Q35_HOST_BRIDGE_PCIEXBAR_SIZE = 256 MiB

对应地址范围是：

::

   0xb0000000 - 0xbfffffff

这块区域不是普通设备寄存器窗口，而是 PCI Express Enhanced Configuration Access Mechanism，通常称为 ECAM
或 MMCONFIG。

传统 PCI 配置空间每个 function 至少暴露 256 字节；PCIe ECAM 则为每个 function 预留 4 KiB：

::

   256 buses
   × 32 devices per bus
   × 8 functions per device
   × 4096 bytes per function
   = 256 MiB

这正好解释了 q35 ``PCIEXBAR`` 的 256 MiB 大小。

mch_mmconfig_setup 为什么分三次写 PCIEXBAR
----------------------------------------

SeaBIOS 执行：

.. code-block:: c

   static void
   mch_mmconfig_setup(u16 bdf)
   {
       u64 addr = 0xb0000000;
       u32 upper = addr >> 32;
       u32 lower = (addr & 0xffffffff) | 1;

       pci_config_writel(bdf, PCIEXBAR, 0);
       pci_config_writel(bdf, PCIEXBAR + 4, upper);
       pci_config_writel(bdf, PCIEXBAR, lower);
       pci_enable_mmconfig(0xb0000000, "q35");
   }

第一步先向低 32 位写零，暂时关闭 PCIEXBAR。随后写入高 32 位，最后把低地址和 enable bit 一起写回。

这样做避免在 64 位基址只更新了一半时，host bridge 短暂启用一个错误窗口。当前地址低于 4 GiB，所以
``upper`` 实际为零，但代码仍按完整的 64 位寄存器更新顺序执行。

最后一位：

::

   PCIEXBAREN = 1

让 q35 开始把 ``0xb0000000`` 这段物理地址解释为 PCIe 配置空间。

SeaBIOS 从端口配置访问切换到 MMCONFIG
----------------------------------

``pci_enable_mmconfig()`` 保存：

.. code-block:: c

   mmconfig = 0xb0000000;

此后，32 位 flat mode 中的 ``pci_config_read*()`` 和 ``pci_config_write*()`` 会优先使用内存映射方式：

.. code-block:: c

   address = mmconfig + (bdf << 12) + register_offset;

例如 ``00:1f.0`` 的 BDF 是 ``0x00f8``。它的配置空间基址是：

::

   0xb0000000 + (0x00f8 << 12)
   = 0xb00f8000

读取寄存器 ``0x10`` 时，实际访问：

::

   0xb00f8010

上一章之所以先使用 ``0xcf8 / 0xcfc``，是因为那时 PCIEXBAR 尚未启用。当前顺序是：

::

   用 0xcf8 / 0xcfc 找到 q35 MCH
   → 识别设备 ID 0x29c0
   → 配置 PCIEXBAR
   → 后续配置访问改走 MMCONFIG

如果代码在 16 位 segmented mode 中运行，或者 MMCONFIG 尚未启用，SeaBIOS 仍会回退到传统配置端口。

MMCONFIG 区域必须进入 E820 保留区
------------------------------

``mch_mem_addr_setup()`` 随后执行：

.. code-block:: c

   e820_add(0xb0000000, 256 * 1024 * 1024, E820_RESERVED);

CPU 对这块地址执行普通内存读写时，q35 会把访问转换成 PCIe 配置事务。它不是可分配给操作系统页框的 RAM。

如果固件只启用 PCIEXBAR，却不在内存地图中保留这段区域，bootloader 或操作系统可能把它误当成普通 RAM，
在其中放置页表、内核数据或用户页面。随后对这些“页面”的访问就会变成 PCI 配置读写，结果将完全错误。

因此同一个硬件动作必须同时反映到两个层面：

::

   host bridge：启用 PCIEXBAR
   E820 map：把相同地址标记为 RESERVED

地址解码和内存所有权描述必须一致。

q35 把 32 位 PCI MMIO 起点推进到 0xc0000000
-----------------------------------------

配置完 256 MiB MMCONFIG 后，SeaBIOS 执行：

.. code-block:: c

   pcimem_start = 0xb0000000 + 0x10000000;

因此：

::

   pcimem_start = 0xc0000000

结合默认上界：

::

   pcimem_end = 0xfec00000

q35 的普通 32 位 PCI MMIO 候选区间成为：

::

   0xc0000000 - 0xfebfffff

它位于 MMCONFIG 之后，又停在 IOAPIC 之前。

``mch_mem_addr_setup()`` 还安装 q35 专用的 INTx pin 到 IRQ 计算函数，并根据 ACPI PM I/O 基址设置 PCI I/O
地址空间的可用下界。这些值会在后面的设备初始化阶段真正使用；当前章节先继续解决 BAR 地址。

BAR 不是设备寄存器本身，而是地址申请表
-----------------------------------

PCI endpoint 需要告诉系统：自己希望占用多大的 I/O port 或 MMIO 地址范围。设备把这项需求编码在 Base Address
Register，也就是 BAR 中。

普通 header type 0 设备最多提供六个 BAR：

::

   BAR0  offset 0x10
   BAR1  offset 0x14
   BAR2  offset 0x18
   BAR3  offset 0x1c
   BAR4  offset 0x20
   BAR5  offset 0x24

另外还有 Expansion ROM BAR。PCI bridge 的 header 布局不同，通常只有两个普通 BAR，并另外包含桥窗口寄存器。

BAR 中既保存地址，也保存属性位：

``I/O BAR``
   bit 0 为 1，表示它请求 I/O port 空间。

``Memory BAR``
   bit 0 为 0，表示它请求 MMIO 空间。

``Prefetchable Memory BAR``
   表示读取没有设备副作用，平台可以采用更积极的预取和合并策略。

``64-bit BAR``
   使用相邻两个 32 位 BAR 寄存器共同保存 64 位基址。

此时 BAR 中可能已有 QEMU 提供的初始值，也可能为零。SeaBIOS 不能只读取当前地址来推断需求，它必须执行 PCI
规范规定的 sizing 操作。

写全 1、读回 mask，为什么能得到 BAR 大小
-------------------------------------

``pci_bios_get_bar()`` 对普通 BAR 保存旧值后写入：

.. code-block:: c

   pci_config_writel(bdf, bar_offset, 0xffffffff);
   val = pci_config_readl(bdf, bar_offset);
   pci_config_writel(bdf, bar_offset, old);

设备不会真的接受所有地址位。它只实现与自身地址窗口大小相符的高位，未实现的低地址位读回零。

假设一个 32 位 MMIO BAR 需要 16 KiB，忽略属性位后可能读回：

::

   0xffffc000

SeaBIOS 使用：

::

   size = ~(val & mask) + 1

于是：

::

   ~(0xffffc000) + 1
   = 0x00004000
   = 16 KiB

同一个结果也说明基址必须按 16 KiB 对齐，因为 BAR 的低 14 个地址位没有被实现。

SeaBIOS 在测量后立即恢复原值，所以 sizing 阶段不会把 ``0xffffffff`` 永久留在设备中。

I/O、普通内存和 prefetchable 内存分开统计
--------------------------------------

``pci_bios_get_bar()`` 根据属性位把每个 BAR 分到三类：

::

   PCI_REGION_TYPE_IO
   PCI_REGION_TYPE_MEM
   PCI_REGION_TYPE_PREFMEM

分开统计的原因是它们不能随意混用：

* I/O BAR 必须落在 x86 I/O port 地址空间；
* 普通 MMIO 可能包含读取即清除等副作用，不应被当作可预取区域；
* prefetchable MMIO 可以进入单独的桥窗口，并可能被放到 4 GiB 以上。

SeaBIOS 还把小于 4 KiB 的 memory BAR 需求提升到至少 4 KiB：

.. code-block:: c

   if (type != IO && size < 4096)
       size = 4096;

这样设备 MMIO 分配至少按页面粒度组织。

64 位 BAR 为什么要跳过下一个 BAR 编号
----------------------------------

64 位 BAR 使用连续两个 32 位寄存器：

::

   BARn      保存地址 bits 31:0
   BARn + 1  保存地址 bits 63:32

SeaBIOS 对低半和高半分别执行全 1 测量，再组合成 64 位 mask。测量完成后：

.. code-block:: c

   if (is64)
       i++;

循环本身还会再增加一次 ``i``，因此高半寄存器不会被错误地当成一个独立 BAR 再处理。

pci_region_entry 保存一次尚未落址的需求
------------------------------------

每个有效 BAR 会变成一个临时 ``pci_region_entry``：

::

   dev       哪个 PCI function
   bar       第几个 BAR
   size      需要多大地址范围
   align     需要怎样对齐
   type      IO / MEM / PREFMEM
   is64      是否为 64 位 BAR

对于普通 BAR，SeaBIOS 当前令：

::

   align = size

这是因为规范化 BAR 大小通常是 2 的幂，其基址需要按同样大小对齐。

这些 entry 被插入对应 bus 的资源链表，并按以下顺序排序：

#. 对齐要求大的在前；
#. 对齐相同的情况下，尺寸大的在前。

先放置更难对齐的大块区域，可以减少后续地址布局中产生无法利用的间隙。

桥窗口要从最深的子总线向根总线汇总
--------------------------------

endpoint BAR 属于设备所在的 bus，但 CPU 的事务若要到达桥后设备，还必须穿过每一级 PCI bridge。每座桥都要
拥有足够大的转发窗口，覆盖其整个下游子树。

SeaBIOS 从 ``MaxPCIBus`` 倒序处理到 bus 1：

.. code-block:: c

   for (secondary_bus = MaxPCIBus;
        secondary_bus > 0;
        secondary_bus--)

这样最深层子总线先计算完成，再把需求上卷到父总线。

假设：

::

   bus 0
   └── bridge A
       └── bus 1
           ├── device X  需要 16 MiB MEM
           └── bridge B
               └── bus 2
                   └── device Y 需要 8 MiB MEM

处理 bus 2 后，bridge B 需要至少 8 MiB memory window。这个 bridge window 本身又成为 bus 1 的一项资源需求。
处理 bus 1 时，bridge A 看到：

::

   16 MiB endpoint BAR
   + bridge B 的下游窗口

于是为整个 bus 1 子树建立更大的上游窗口。

桥资源 entry 使用 bar = -1
-------------------------

普通 endpoint BAR 的 entry 保存真实 BAR 编号。桥窗口不是 BAR0 到 BAR5，而是 header type 1 中的：

::

   I/O Base / I/O Limit
   Memory Base / Memory Limit
   Prefetchable Memory Base / Limit

SeaBIOS 因此用：

::

   entry->bar = -1

标记“这不是 endpoint BAR，而是一段桥转发窗口”。映射阶段看到 ``bar == -1`` 时，会写 bridge base/limit
寄存器，而不是调用普通 BAR 写入函数。

桥窗口有最低对齐粒度
------------------

SeaBIOS 为桥资源设置最低对齐：

::

   I/O bridge window     4 KiB
   MEM bridge window     2 MiB
   PREFMEM bridge window 2 MiB

实际要求如果更高，就采用子设备中最大的对齐值。

桥窗口粒度通常大于单个小 BAR，所以多个下游设备的需求需要先求和，再整体向上对齐。这里的填充不是浪费式随机
留白，而是为了让桥寄存器能准确表达一整段连续转发范围。

热插拔桥必须给未来设备留空间
--------------------------

SeaBIOS 检查 PCIe capability 或 SHPC capability，判断桥后是否支持热插拔。

如果一座桥当前后面没有设备，而固件只为“当前已存在设备”分配零大小窗口，那么系统启动后再热插入设备时，
操作系统可能找不到可在该桥下扩展的地址范围。

因此 SeaBIOS 对支持热插拔的桥加入最低 padding。QEMU 还可以通过 Red Hat vendor-specific resource reserve
capability，明确告诉固件应额外保留多少：

::

   bus numbers
   I/O space
   non-prefetchable memory
   32-bit prefetchable memory
   64-bit prefetchable memory

这意味着 PCI 地址规划不只描述开机瞬间已有的设备，还需要为运行时可能出现的设备保留拓扑和资源余量。其中bus
number reserve已经在上一章的递归编号阶段写入bridge subordinate；本章读取的是I/O、MEM和PREFMEM reserve，
不能把两次操作混成同一处寄存器更新。

桥能力探测会暂时关闭部分旧窗口
--------------------------------

``pci_bridge_has_region()`` 检查bridge是否能表达I/O或PREFMEM窗口时，会向相应base寄存器写 ``0xff`` 再读回；
源码明确把“禁用bridge window”列为这个探测的副作用。普通MEM窗口是规范要求的能力，不走这次写探测。

所以 ``pci_bios_check_devices()`` 不只是读取需求：endpoint BAR的sizing值会恢复，但部分bridge旧窗口会先被置成
无效状态。成功路径随后由 ``pci_bios_map_devices()`` 写入新的base/limit覆盖它们；若临时分配中途失败，源码没有
在本函数内恢复一套旧bridge映射。

第一轮结束时地址尚未重新分配
----------------------------

``pci_bios_check_devices()`` 完成后，SeaBIOS 已经知道：

* 每个 endpoint BAR 的类型、大小和对齐；
* 每条子总线的总资源需求；
* 每座桥需要多大的 I/O、MEM 和 PREFMEM 窗口；
* 哪些桥需要热插拔预留；
* 哪些 BAR 可以使用 64 位地址。

但entry中仍然没有最终基址；除上面的bridge能力探测副作用外，endpoint BAR原值已经恢复。第一轮主要解决的是：

::

   需要多少空间？

第二轮 ``pci_bios_map_devices()`` 才解决：

::

   每一段空间放在哪里？

根总线 I/O 空间优先使用 0xc000-0xffff
------------------------------------

SeaBIOS 先计算全部 PCI I/O BAR 和桥 I/O window 的总和。

如果总需求小于 16 KiB，就使用传统区域：

::

   0xc000 - 0xffff

如果不够，且较低区域仍能容纳，则改从：

::

   0x1000

开始分配。``pci_io_low_end`` 决定这段较低空间在哪里结束，避免覆盖 ACPI PM I/O 等平台保留端口。

两段都放不下时，SeaBIOS 会直接报 ``PCI: out of I/O address space``，因为 I/O port 空间只有 16 位，不能像
MMIO 一样简单扩展到更高物理地址。

32 位 MMIO 从窗口高端向下安排
-------------------------

q35 当前 32 位 MMIO 窗口是：

::

   0xc0000000 - 0xfebfffff

SeaBIOS 分别统计普通 MEM 和 PREFMEM 需求，再从 ``pcimem_end`` 向低地址排列：

.. code-block:: c

   region_end.base = ALIGN_DOWN(pcimem_end - end_sum,
                                end_align);
   region_start.base = ALIGN_DOWN(region_end.base - start_sum,
                                  start_align);

哪一类区域具有更大的对齐要求，会被放到更适合的位置，以减少对齐空洞。

如果计算出的最低基址落到 ``pcimem_start`` 以下，说明32位MMIO窗口无法容纳全部需求，SeaBIOS会尝试把合格的
64位entry迁移到4 GiB以上。另一个独立触发条件是 ``pci_pad_mem64``：它为真时，即使32位窗口原本放得下，代码也
进入迁移分支，为高端窗口及热插拔余量执行布局。迁移后32位区域仍放不下会触发 ``panic``，不是返回一个可继续的
“部分成功”状态。

哪些 64 位 BAR可以迁移到 4 GiB 以上
---------------------------------

SeaBIOS 从 MEM 和 PREFMEM 链表中挑出 ``is64`` 的 entry，放入单独的 64 位区域。

源码明确排除两类设备：

::

   PCI_CLASS_SERIAL_USB
   PCI_CLASS_STORAGE_NVME

也就是说，即使 USB 控制器或 NVMe 控制器暴露 64 位 BAR，这段 SeaBIOS 代码也不会把它们迁移到高地址列表。
源码在这里没有给出完整设计理由，本章不额外推断；可以确认的是，SeaBIOS 固件驱动阶段仍要求这些控制器保持在
其可直接处理的低地址范围。

64 位窗口从高端 RAM 之后起算
----------------------------

64 位 MMIO 起点至少位于：

::

   4 GiB + RamSizeOver4G

也就是所有 4 GiB 以上客户机 RAM 的末端之后。

SeaBIOS 还会考虑：

* QEMU ``etc/reserved-memory-end``；
* CPU 物理地址位数决定的 ``pci_mem64_top``；
* E820 中已经占用的高地址区域；
* BAR 自身对齐；
* 1 GiB 边界对齐。

最终得到：

::

   pcimem64_start
   pcimem64_end

只有 ``pci_pad_mem64`` 为假且32位布局一次成功、因而根本不进入迁移分支时， ``else`` 才明确把
``pcimem64_start`` 清零。padding为真时会进入高端计算，即使某个具体机器恰好没有可迁移的endpoint BAR，也不能仅凭
“没有这个BAR”推断该变量必定为0；应以该分支实际汇总的entry和最终 ``pcimem64_start/end`` 为准。

为什么 64 位窗口按 1 GiB 对齐
---------------------------

代码对高地址 MEM 和 PREFMEM 基址都执行：

.. code-block:: c

   ALIGN(value, 1ULL << 30)

也就是按 1 GiB 对齐。这样会使大型 PCI MMIO 窗口更规整，并与大页友好的地址边界一致。

这不代表每个 BAR 都占 1 GiB；单个 BAR 仍按自己的 ``size`` 和 ``align`` 放置。1 GiB 对齐针对的是高端区域整体
起点和边界。

第二轮怎样真正写入 endpoint BAR
------------------------------

``pci_region_map_entries()`` 依次取出已经排序的 entry：

.. code-block:: c

   addr = region->base;
   region->base += entry->size;

普通 BAR 的 entry 调用：

.. code-block:: c

   pci_set_io_region_addr(dev, bar, addr, is64);

32 位 BAR 写一个配置寄存器。64 位 BAR 还会把：

::

   addr >> 32

写入相邻的高 32 位 BAR。

此后设备配置空间已经保存该地址，但设备是否响应 CPU 对这段地址的访问，还取决于后面的 ``PCI_COMMAND_IO`` 或
``PCI_COMMAND_MEMORY`` 使能位。

桥窗口怎样写入 base 和 limit
--------------------------

当 entry 的 ``bar == -1`` 时，SeaBIOS 将它解释为 bridge window。

对于 I/O window，写入：

::

   PCI_IO_BASE
   PCI_IO_LIMIT

对于普通 memory window，写入：

::

   PCI_MEMORY_BASE
   PCI_MEMORY_LIMIT

对于 prefetchable memory window，写入：

::

   PCI_PREF_MEMORY_BASE
   PCI_PREF_MEMORY_LIMIT
   PCI_PREF_BASE_UPPER32
   PCI_PREF_LIMIT_UPPER32

``limit`` 计算为：

::

   limit = base + size - 1

所以桥会转发整个闭区间 ``[base, limit]``。如果桥后还有下一层桥，父桥窗口覆盖子桥窗口，CPU 的事务才能逐层到达
最终 endpoint。

父桥窗口先确定子总线的起点
-----------------------

映射一个桥 entry 时，SeaBIOS 还会执行：

.. code-block:: c

   busses[entry->dev->secondary_bus].r[entry->type].base = addr;

这把父桥分配到的窗口起点交给对应子总线。稍后遍历这条子总线时，endpoint BAR 和更深层桥窗口就从该起点继续
顺序分配。

地址因此沿拓扑逐级落实：

::

   根总线区域获得全局基址
   → 父桥获得一段连续窗口
   → 子总线继承窗口起点
   → 子设备 BAR 在窗口内部落址
   → 更深层桥继续分割自己的子窗口

设备地址和桥转发范围由同一组临时资源 entry 生成，不会分别独立计算后再碰运气匹配。

地址写入完成仍不代表设备已经启动
--------------------------------

``pci_bios_map_devices()`` 返回时，SeaBIOS 已经完成：

* q35 MMCONFIG 启用；
* MMCONFIG E820 保留；
* BAR sizing；
* I/O、32 位 MMIO、64 位 MMIO 规划；
* endpoint BAR 地址写入；
* bridge I/O、MEM、PREFMEM window 写入。

仍未完成：

``PCI_INTERRUPT_LINE``
   INTx pin 尚未统一映射到 q35 的 IRQ line。

``PCI_COMMAND``
   I/O decode、memory decode 和 SERR 尚未由统一初始化阶段开启。

``device-specific setup``
   ICH9 LPC、IDE、SMBus 等设备的专用寄存器配置尚未全部执行。

``driver probe``
   ATA、AHCI、NVMe、USB、virtio 等 SeaBIOS 驱动尚未开始寻找介质。

``BootList``
   尚无具体磁盘、光驱或网络启动项。

BAR 获得地址只代表“设备未来应在这里响应”。后续还要打开地址解码、初始化控制器，并由驱动实际访问这些寄存器。

本章结束状态
------------

控制权目前走过：

::

   qemu_platform_setup()
   → pci_setup()
   → pcimem_start = RamSize
   → pci_bios_init_platform()
   → 匹配 q35 MCH 00:00.0
   → mch_mem_addr_setup()
   → 启用 0xb0000000-0xbfffffff MMCONFIG
   → 将 MMCONFIG 加入 E820_RESERVED
   → pcimem_start = 0xc0000000
   → pci_bios_check_devices()
   → 测量 endpoint BAR
   → 自底向上汇总 bridge window
   → pci_bios_map_devices()
   → 分配 I/O、32 位 MMIO 和 64 位 MMIO
   → 写入 endpoint BAR 与 bridge base/limit

此刻：

* 当前执行者：SeaBIOS ``pci_setup()``；
* 当前 CPU：BSP；
* CPU 模式：32 位保护模式；
* 分页：关闭；
* A20：开启；NMI：仍由CMOS index bit 7屏蔽；
* 可屏蔽中断：主控制流IF仍为0，PIC mask未因BAR映射改变；
* SeaBIOS线程：仍只有 ``MainThread``，没有并行PCI配置线程；
* PCI 配置访问：32 位 flat mode 已切换到 q35 MMCONFIG；
* MMCONFIG：``0xb0000000-0xbfffffff``，已标记 ``E820_RESERVED``；
* 32 位 PCI MMIO 候选窗口：从 ``0xc0000000`` 到 ``0xfec00000`` 之前；
* endpoint BAR 大小和类型：已经测量；
* endpoint BAR 地址：已经写入；
* PCI bridge I/O、MEM 和 PREFMEM 窗口：已经写入；
* 可用的 64 位 BAR：可能已经分配到 4 GiB 以上；
* PCI INTx routing：尚未统一写入；
* ``PCI_COMMAND`` 地址解码：尚未统一开启；
* q35/ICH9 设备专用初始化：尚未全部执行；
* PCI 设备驱动：尚未运行；
* 磁盘、光驱、USB 与网络启动设备：尚未探测；
* ``BootList``：尚无具体启动设备；
* GRUB：尚未被读取或执行；
* Linux：尚未装入内存。

关键边界
--------

* PCIEXBAR寄存器启用与E820保留必须描述同一物理范围；ECAM不是普通RAM或endpoint BAR；
* BAR sizing对endpoint寄存器写探测值后恢复，bridge能力探测却会禁用部分旧窗口，成功映射阶段再覆盖；
* bridge资源必须先从深层bus向上汇总，再从root向下分配；两个方向不能互换；
* 高端迁移既可能由32位空间不足触发，也可能由 ``pci_pad_mem64`` 主动触发；USB和NVMe class仍留在低地址列表；
* BAR与bridge窗口写入不等于 ``PCI_COMMAND`` 已经开启，更不等于bus mastering或控制器驱动已经启动；
* 本章成功出口要求临时分配与地址空间检查通过；源码的失败路径不是完整回滚。

下一入口
--------

``pci_bios_map_devices()`` 返回后，下一条调用是：

.. code-block:: c

   pci_bios_init_devices();

下一章将为每个 PCI function 写入 INTx line，执行 q35/ICH9 设备专用初始化，并打开 I/O、memory 和 SERR 解码。

资料
----

* `SeaBIOS固定提交：Q35 MMCONFIG和PCI窗口起点 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/pciinit.c#L470-L527>`_；
* `SeaBIOS固定提交：ECAM与传统配置访问选择 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/pci.c#L17-L134>`_；
* `SeaBIOS固定提交：BAR测量、64位判断和entry排序 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/pciinit.c#L673-L800>`_；
* `SeaBIOS固定提交：固件驱动拒绝4 GiB以上memory BAR <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/pcidevice.c#L166-L191>`_；
* `SeaBIOS固定提交：bridge能力、热插拔与资源上卷 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/pciinit.c#L803-L1003>`_；
* `SeaBIOS固定提交：32位与64位区域规划 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/pciinit.c#L1010-L1169>`_；
* `SeaBIOS固定提交：endpoint BAR与bridge窗口落址 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/pciinit.c#L1064-L1177>`_；
* `SeaBIOS固定提交：PCI分配主调用及失败出口 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/pciinit.c#L1184-L1247>`_；
* `QEMU固定提交：q35 PCIEXBAR地址、长度和enable解码 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/pci-host/q35.c#L300-L335>`_；
* `QEMU固定提交：q35低RAM为MMCONFIG和PCI MMIO留洞 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/pc_q35.c#L155-L192>`_；
* `QEMU固定提交：q35 MCH低RAM末端到IOAPIC的PCI hole <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/pci-host/q35.c#L507-L525>`_。
