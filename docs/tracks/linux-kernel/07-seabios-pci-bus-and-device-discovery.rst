第七章：SeaBIOS 怎样为 q35 编号 PCI 总线并发现设备？
===================================================

上一章结束时，SeaBIOS 已经复位传统 DMA、初始化 8259A、建立内部协作式线程能力，并为旧式数学协处理器
异常装好 ``INT 75h`` 兼容入口。控制流仍在：

::

   post.c:platform_hardware_setup()

下一条调用是：

.. code-block:: c

   qemu_platform_setup();

这一调用并不会立即找到硬盘，更不会进入 GRUB。它首先要把 QEMU q35 暴露出来的 PCI/PCIe 拓扑变成
SeaBIOS 能够操作的设备列表。

本章沿下面的真实控制流前进：

::

   qemu_platform_setup()
   → 排除 Xen 专用分支
   → kvmclock_init()
   → pci_setup()
   → 记录 64 位 PCI 资源窗口策略
   → pci_probe_host()
   → pci_bios_init_bus()
   → pci_probe_devices()

本章结束在 ``pci_probe_devices()`` 返回。此时 SeaBIOS 已经知道总线上存在哪些设备、设备位于哪个
``bus:device.function``、哪些设备是桥以及桥后面连接了哪些总线；它还没有为设备分配 BAR 地址，也没有开始
运行磁盘、USB 或网络驱动。

本章固定使用：

::

   repository: coreboot/seabios
   commit: c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf

qemu_platform_setup 先区分普通 QEMU 与 Xen
------------------------------------------

``qemu_platform_setup()`` 位于 ``src/fw/paravirt.c``：

.. code-block:: c

   void
   qemu_platform_setup(void)
   {
       if (!CONFIG_QEMU)
           return;

       if (runningOnXen()) {
           pci_probe_devices();
           xen_hypercall_setup();
           xen_biostable_setup();
           return;
       }

       kvmclock_init();

       pci_setup();
       smm_device_setup();
       smm_setup();

       mtrr_setup();
       msr_feature_control_setup();
       smp_setup();

       /* 后面还有固件表初始化 */
   }

当前主线是普通 QEMU q35，不是 Xen HVM。因此 ``runningOnXen()`` 为假，控制流不会进入 Xen 的 hypercall
和 Xen BIOS table 分支。

这说明同一个函数名下面存在多条平台路径。书中的控制流不能只看调用表面，还要结合前面已经建立的
``PlatformRunningOn`` 状态，判断当前究竟执行哪一条分支。

kvmclock_init 是条件路径
-----------------------

普通 QEMU 路径首先调用：

.. code-block:: c

   kvmclock_init();

这个名字容易让人以为所有 QEMU 虚拟机都会建立 KVM 时钟。实际第一条判断是：

.. code-block:: c

   if (!runningOnKVM())
       return;

QEMU 可以使用不同执行后端：

* KVM 使用 Linux 内核的硬件虚拟化能力运行客户机；
* TCG 由 QEMU 进行指令翻译；
* 其他宿主平台也可能使用不同加速后端。

SeaBIOS 在前面的 ``kvm_detect()`` 中通过 hypervisor CPUID 签名 ``KVMKVMKVM`` 判断 KVM 是否存在。
没有该标记时，``kvmclock_init()`` 立即返回，后面的 PCI 主线不受影响。

如果当前确实运行在 KVM 上，SeaBIOS 会继续读取 KVM feature bits，选择系统时间 MSR：

::

   MSR_KVM_SYSTEM_TIME_NEW = 0x4b564d01
   MSR_KVM_SYSTEM_TIME     = 0x00000012

然后分配一个 32 字节对齐的 ``pvclock_vcpu_time_info`` 结构，把它的物理地址最低位设为 1，再写入选中的 MSR：

.. code-block:: c

   kvmclock = memalign_low(sizeof(*kvmclock), 32);
   memset(kvmclock, 0, sizeof(*kvmclock));
   wrmsr(msr, (u32)kvmclock | 0x01);

最低位的 ``1`` 表示启用这份共享时间信息。KVM 随后可以更新结构中的时间换算参数。如果结构声明 TSC 稳定，
SeaBIOS 会据此计算 TSC 频率，供自己的延时与计时代码使用。

这一步只是在 KVM 条件下改善固件计时。它没有启动 Linux 的 paravirtual clock，也没有向 GRUB 交出控制权。

pci_setup 先保存后续资源分配策略
-------------------------------

随后进入：

.. code-block:: c

   pci_setup();

``pci_setup()`` 的开头还没有扫描设备。它先保存稍后分配 PCI 64 位内存窗口时要使用的策略。

前面 ``qemu_preinit()`` 已经通过 CPUID 得到：

``CPUPhysBits``
   CPU 支持的物理地址位数。

``CPULongMode``
   CPU 是否支持 x86-64 long mode。

``pci_setup()`` 据此计算：

.. code-block:: c

   pci_mem64_top = 1LL << CPUPhysBits;

这个值表示理论上能够用于 64 位 PCI MMIO 窗口的物理地址上界。

源码还包含一项兼容限制：当 CPU 报告超过 44 个物理地址位、而客户机 4 GiB 以上 RAM 少于 1 TiB 时，
SeaBIOS 把 PCI 64 位窗口上界限制到：

::

   1 << 44 = 16 TiB

原因不是硬件只能访问 16 TiB，而是某些旧 Linux 内核和旧 virtio-pci 驱动无法正确处理过高的 PCI BAR 地址。
这项限制说明固件分配地址时不仅要服从硬件能力，也要考虑将要启动的软件生态。

SeaBIOS 接着读取：

::

   opt/org.seabios/pci64

它决定是否为可放到 4 GiB 以上的 PCI BAR 预留 64 位窗口。没有显式配置时，只要客户机存在 4 GiB 以上 RAM，
默认就允许该窗口；如果 CPU 不支持 long mode，则强制关闭。

这些变量将在下一阶段分配 BAR 时使用。本章当前只记录策略，还没有给任何设备写入地址。

PCI 设备怎样向软件描述自己
------------------------

PCI 设备不是依靠 SeaBIOS 猜测型号。每个 PCI function 都有一块 configuration space，也就是配置空间。
传统 PCI 配置空间至少提供 256 字节，其中前 64 字节布局标准化。

常见字段包括：

::

   offset 0x00  vendor ID
   offset 0x02  device ID
   offset 0x04  command
   offset 0x06  status
   offset 0x08  revision ID
   offset 0x09  programming interface
   offset 0x0a  class / subclass
   offset 0x0e  header type
   offset 0x10  BAR0
   ...

设备厂商 ID 和设备 ID回答“它是谁”；class、subclass 和 programming interface 回答“它是哪一类设备以及采用
什么编程接口”；header type 回答“它是普通设备、PCI-to-PCI bridge 还是 CardBus bridge”。

SeaBIOS 当前的任务是先读出身份和拓扑。BAR、command 和 interrupt line 等字段要在后续阶段配置。

BDF 是 PCI function 的地址
-------------------------

PCI 配置访问使用三个层级定位一个 function：

``bus``
   总线号，8 位，可表示 0 到 255。

``device``
   一条总线上的设备号，5 位，可表示 0 到 31。

``function``
   一个 device 内的 function 号，3 位，可表示 0 到 7。

通常写成：

::

   bus:device.function

例如 q35 host bridge 位于：

::

   00:00.0

ICH9 LPC bridge 常见位置是：

::

   00:1f.0

SeaBIOS 把这三部分压成一个 16 位 ``bdf``：

.. code-block:: c

   bdf = (bus << 8) | (device << 3) | function;

对应拆解函数是：

.. code-block:: c

   bus      = bdf >> 8;
   device   = (bdf >> 3) & 0x1f;
   function = bdf & 0x07;

以 ``00:1f.0`` 为例：

::

   bus      = 0x00
   device   = 0x1f
   function = 0

   bdf = (0x00 << 8) | (0x1f << 3) | 0
       = 0x00f8

BDF 不是普通内存地址。它是构造 PCI 配置访问请求时使用的设备坐标。

早期 q35 枚举仍然使用 0xcf8 和 0xcfc
----------------------------------

PCI Express 支持 ECAM/MMCONFIG：每个 function 占 4 KiB 内存映射配置空间。但 SeaBIOS 当前还没有配置 q35
host bridge 的 ``PCIEXBAR``，所以本章的早期枚举仍使用传统 PCI Configuration Mechanism #1。

相关 I/O 端口是：

::

   0x0cf8  CONFIG_ADDRESS
   0x0cfc  CONFIG_DATA

SeaBIOS 构造 ``CONFIG_ADDRESS`` 的代码是：

.. code-block:: c

   return 0x80000000 | (bdf << 8) | (addr & 0xfc);

展开后就是：

::

   bit 31      enable
   bit 23:16   bus
   bit 15:11   device
   bit 10:8    function
   bit 7:2     configuration register dword offset
   bit 1:0     0

访问过程分两步：

#. 向 ``0xcf8`` 写入包含 BDF 和寄存器偏移的配置地址；
#. 从 ``0xcfc`` 读取或写入数据。

例如读取 ``00:1f.0`` 的 vendor/device ID，寄存器偏移为 ``0x00``：

::

   bdf << 8 = 0x0000f800

   CONFIG_ADDRESS
   = 0x80000000 | 0x0000f800 | 0x00
   = 0x8000f800

CPU 先执行：

::

   OUT 0xcf8, 0x8000f800

再从 ``0xcfc`` 读取 32 位值。低 16 位是 vendor ID，高 16 位是 device ID。

在 QEMU 中，这些 ``IN`` 和 ``OUT`` 指令不会到达真实主板。QEMU 的 q35/ICH9 设备模型解释端口访问，并返回
对应虚拟 PCI function 的配置空间内容。

pci_probe_host 只确认配置机制存在
--------------------------------

SeaBIOS 在正式编号总线前调用：

.. code-block:: c

   if (pci_probe_host() != 0)
       return;

``pci_probe_host()`` 很短：

.. code-block:: c

   outl(0x80000000, 0x0cf8);
   if (inl(0x0cf8) != 0x80000000)
       return -1;
   return 0;

它把 enable bit 写入 CONFIG_ADDRESS 端口，再读回来。如果读回值不同，SeaBIOS 认为当前平台不支持这种 PCI
配置访问方式。

这一步没有发现任何设备。它只确认：

::

   SeaBIOS 可以通过 0xcf8 / 0xcfc 发出 PCI 配置请求

下一步才开始处理总线拓扑。

为什么必须先给桥后面的总线编号
----------------------------

根总线通常从 bus 0 开始。直接挂在 bus 0 上的设备可以立刻用 BDF 访问。

PCI-to-PCI bridge 的另一侧还连接着一条 secondary bus。配置请求能否穿过桥，取决于桥配置空间中的三个字段：

``Primary Bus Number``
   桥上游所在的总线号。

``Secondary Bus Number``
   桥下游紧邻的第一条总线号。

``Subordinate Bus Number``
   这座桥后面能够到达的最大总线号。

只有目标 bus 满足桥的 secondary 到 subordinate 范围，桥才会向下游转发配置访问。

QEMU 可以在虚拟机创建时放好设备对象，但 SeaBIOS 仍需要建立一套一致的总线编号。否则固件无法用稳定 BDF
访问桥后的设备，后续也无法生成 ACPI 和 PCI routing 信息。

pci_bios_init_bus 从 bus 0 递归编号
---------------------------------

SeaBIOS 调用：

.. code-block:: c

   pci_bios_init_bus();

内部从根总线开始：

.. code-block:: c

   u8 pci_bus = 0;
   pci_bios_init_bus_rec(0, &pci_bus);

递归函数对每条总线执行两轮扫描。

第一轮先关闭所有桥的下游窗口
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

第一轮找到当前 bus 上所有 PCI-to-PCI bridge，然后写入：

.. code-block:: c

   secondary_bus   = 255;
   subordinate_bus = 0;

这是一个无效范围：

::

   secondary 255 > subordinate 0

因此桥不会把当前配置访问错误地转发到尚未编号的下游设备。

源码注释把目的写成：

::

   prevent accidental access to unintended devices

在重新编号前先关闭旧路由，可以避免多个桥暂时把同一个 bus 号指向不同下游，导致配置请求落到错误设备。

第二轮逐桥分配 secondary bus
~~~~~~~~~~~~~~~~~~~~~~~~~~~

第二轮再次遍历桥设备。对每座桥：

#. 把 ``Primary Bus Number`` 改成当前 bus；
#. 把全局 ``pci_bus`` 增加 1；
#. 把新值写入 ``Secondary Bus Number``；
#. 临时把 ``Subordinate Bus Number`` 写成 255；
#. 递归扫描新的 secondary bus；
#. 递归结束后，把 subordinate 缩小到实际使用的最大 bus。

临时写入 255 的原因与第一轮相反。递归扫描时，SeaBIOS 尚不知道桥后面最终会用到多少级总线，因此先把最大
范围开放到 255，让配置请求能够穿过这座桥继续发现更深层桥。递归返回后，已经得到真实最大 bus，再收紧范围。

假设拓扑是：

::

   bus 0
   ├── bridge A
   │   └── bus 1
   │       └── bridge B
   │           └── bus 2
   └── device C

编号过程大致是：

::

   bridge A:
      primary     = 0
      secondary   = 1
      subordinate = 255   # 临时

   bridge B:
      primary     = 1
      secondary   = 2
      subordinate = 255   # 临时

   bus 2 扫描完成
      bridge B subordinate = 2

   bus 1 扫描完成
      bridge A subordinate = 2

最终发送给 bus 2 的配置请求，可以依次穿过 A 和 B；发送给 bus 3 的请求不会被 A 继续转发。

额外 root bus 是可选路径
----------------------

``pci_bios_init_bus()`` 还读取：

::

   etc/extra-pci-roots

某些虚拟平台可能暴露不经过 bus 0 桥链的额外根总线。配置为非零时，SeaBIOS 会继续尝试更多 root bus。

普通 q35 主线通常从 bus 0 的根复合体展开。这项参数保留了处理复杂虚拟拓扑的能力，不能把“PCI 永远只有一个
root bus”写成架构规则。

总线编号完成后才建立设备缓存
--------------------------

桥的 primary、secondary 和 subordinate bus 已经稳定后，``pci_setup()`` 才打印：

::

   === PCI device probing ===

然后调用：

.. code-block:: c

   pci_probe_devices();

这一次扫描的目的不再是修改总线号，而是为每个存在的 PCI function 创建 ``struct pci_device``，加入全局
``PCIDevices`` 链表。

pci_next 怎样跳过不存在的 function
----------------------------------

每条总线最多包含：

::

   32 devices × 8 functions = 256 functions

直接对所有 256 个位置做完整初始化可以工作，但很多 device 只有 function 0。SeaBIOS 使用 ``pci_next()``
减少无意义访问。

对于一个已经找到的 function 0，它读取 ``PCI_HEADER_TYPE``：

.. code-block:: c

   if (function == 0 && !(header_type & 0x80))
       bdf += 8;
   else
       bdf += 1;

``header_type`` 的最高位是 multi-function bit：

* 该位为 0：这个 device 只有 function 0，直接跳到下一个 device；
* 该位为 1：继续检查 function 1 到 function 7。

对于候选 BDF，SeaBIOS读取 vendor ID：

.. code-block:: c

   vendor = pci_config_readw(bdf, PCI_VENDOR_ID);

下面两个值被视为“该 function 不存在”：

::

   0xffff
   0x0000

如果 function 不存在，扫描器继续前进；如果 vendor ID 是有效值，当前 BDF 就被认定为一个存在的 PCI function。

pci_probe_devices 为每个 function 保存什么
-----------------------------------------

找到一个 function 后，SeaBIOS 从临时 POST 内存分配：

.. code-block:: c

   struct pci_device

结构中保存：

::

   bdf
   rootbus
   parent bridge pointer

   vendor ID
   device ID
   class / subclass
   programming interface
   revision
   header type
   secondary bus number

源码首先一次读取 vendor 和 device：

.. code-block:: c

   u32 vendev = pci_config_readl(bdf, PCI_VENDOR_ID);
   dev->vendor = vendev & 0xffff;
   dev->device = vendev >> 16;

然后一次读取 class、programming interface 和 revision：

.. code-block:: c

   u32 classrev = pci_config_readl(bdf, PCI_CLASS_REVISION);
   dev->class    = classrev >> 16;
   dev->prog_if  = classrev >> 8;
   dev->revision = classrev;

赋值到较窄字段时会保留对应低位，因此最终拆成：

::

   bits 31:16  class + subclass
   bits 15:8   programming interface
   bits 7:0    revision

最后读取：

.. code-block:: c

   dev->header_type = pci_config_readb(bdf, PCI_HEADER_TYPE);

如果低 7 位表示 PCI bridge 或 CardBus bridge，还会读取它的 ``Secondary Bus Number``。

设备列表不只是一个平面数组
------------------------

``pci_probe_devices()`` 同时维护：

.. code-block:: c

   struct pci_device *busdevs[256];

当发现桥时：

.. code-block:: c

   busdevs[secondary_bus] = bridge;

稍后扫描这条 secondary bus 上的设备，就能把：

.. code-block:: c

   dev->parent = busdevs[bus];

设置成真正的上游桥。

因此 ``PCIDevices`` 不只回答“有哪些设备”，还保留树形拓扑：

::

   root bus
   ├── endpoint
   ├── bridge
   │   ├── endpoint
   │   └── bridge
   │       └── endpoint
   └── endpoint

``rootbus`` 字段则标记设备属于哪一个 PCI root。普通单 root q35 中，主要设备属于 root 0；存在额外 root bus
时，它们会得到不同 root 编号。

MaxPCIBus 怎样随扫描增长
----------------------

``pci_probe_devices()`` 从 bus 0 开始。初始时它不需要假设最大 bus 是 255。

每发现一座桥，就读取：

.. code-block:: c

   secondary_bus

如果该值大于当前 ``MaxPCIBus``，就更新最大值。外层循环随后继续扫描新出现的 bus。

所以设备扫描不是：

::

   盲目读取 0 到 255 的所有总线

而是：

::

   从已知 root 开始
   → 发现桥
   → 得到新的 secondary bus
   → 扩展扫描范围
   → 继续发现更深层设备

这与前面的递归编号共同构成闭环：编号阶段让桥后总线可达，设备探测阶段再把可达拓扑缓存成 C 数据结构。

为什么 q35 到现在还没有启用 MMCONFIG
-----------------------------------

q35 host bridge 支持 PCI Express ECAM。SeaBIOS 源码为它准备的窗口是：

::

   base = 0xb0000000
   size = 256 MiB

每个 BDF 占 4 KiB：

::

   mmconfig address = base + (bdf << 12) + register offset

但启用这块窗口的 ``mch_mem_addr_setup()`` 属于下一步：

.. code-block:: c

   pcimem_start = RamSize;
   pci_bios_init_platform();

当前章节停在 ``pci_probe_devices()`` 返回，因此：

* q35 MCH 已经作为 ``00:00.0`` 被发现并放入 ``PCIDevices``；
* SeaBIOS 还没有通过设备匹配调用 ``mch_mem_addr_setup()``；
* ``PCIEXBAR`` 尚未由本阶段配置；
* 本章的总线编号和设备身份读取都走 ``0xcf8 / 0xcfc``。

这是一处重要的时间顺序：

::

   先用传统配置端口找到 q35 host bridge
   → 再根据它的 vendor/device ID 识别平台
   → 然后才启用 PCIe MMCONFIG

不能反过来说“因为是 q35，所以固件一开始就已经使用 ECAM”。

发现设备不等于设备已经可以工作
----------------------------

``pci_probe_devices()`` 返回时，SeaBIOS 只完成了身份和拓扑发现。

尚未完成的事情包括：

``BAR sizing``
   还没有通过写入全 1、读回 mask 的方式确定每个 BAR 需要多大空间。

``BAR assignment``
   还没有为 I/O BAR、32 位 MMIO BAR 和 64 位 prefetchable BAR 分配地址。

``bridge windows``
   还没有为每座桥设置 I/O、memory 和 prefetchable memory 转发窗口。

``interrupt routing``
   还没有把 PCI INTx pin 映射到具体 IRQ line。

``PCI command``
   还没有统一打开设备的 I/O decode、memory decode 和 SERR。

``device drivers``
   USB、ATA、AHCI、NVMe、virtio、网络等驱动尚未探测或启动。

``BootList``
   还没有具体硬盘、光驱或网络启动项被注册。

因此此时看到一块存储控制器的 ``vendor/device ID``，只代表 SeaBIOS 知道它存在。控制器后面的磁盘介质是否存在、
怎样读扇区、是否包含 GRUB，都还没有被处理。

第七章结束时的机器状态
--------------------

控制权目前走过：

::

   platform_hardware_setup()
   → qemu_platform_setup()
   → 排除 Xen 分支
   → kvmclock_init()
   → pci_setup()
   → 记录 PCI 64 位资源窗口策略
   → pci_probe_host()
   → 验证 0xcf8 / 0xcfc 配置机制
   → pci_bios_init_bus()
   → 递归分配 primary / secondary / subordinate bus
   → pci_probe_devices()
   → 扫描存在的 PCI functions
   → 建立 PCIDevices 链表和 parent bridge 关系

此刻：

* 当前执行者：SeaBIOS ``pci_setup()``；
* 当前 CPU：BSP；
* CPU 模式：32 位保护模式；
* 分页：关闭；
* PCI 配置访问：仍使用 ``0xcf8 / 0xcfc``；
* PCI bus number：已经分配；
* PCI bridge 上下游关系：已经确定；
* ``PCIDevices``：已经保存设备身份与拓扑；
* q35 MMCONFIG：尚未启用；
* PCI BAR：尚未测量和分配；
* PCI INTx routing：尚未写入；
* PCI 设备驱动：尚未运行；
* 磁盘与其他启动设备：尚未探测；
* ``BootList``：尚无具体启动设备；
* GRUB：尚未被读取或执行；
* Linux：尚未装入内存。

``pci_probe_devices()`` 返回后，``pci_setup()`` 的下一条语句是：

.. code-block:: c

   pcimem_start = RamSize;
   pci_bios_init_platform();

下一段将识别刚刚发现的 q35 MCH，启用位于 ``0xb0000000`` 的 MMCONFIG 窗口，然后测量每个设备的 BAR
需求，为整棵 PCI 拓扑分配 I/O 和 MMIO 地址。

资料
----

* `SeaBIOS src/fw/paravirt.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/paravirt.c>`_；
* `SeaBIOS src/fw/pciinit.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/pciinit.c>`_；
* `SeaBIOS src/fw/dev-q35.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/dev-q35.h>`_；
* `SeaBIOS src/hw/pci.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/pci.c>`_；
* `SeaBIOS src/hw/pci.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/pci.h>`_；
* `SeaBIOS src/hw/pcidevice.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/pcidevice.c>`_；
* `SeaBIOS src/hw/pcidevice.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/pcidevice.h>`_；
* `SeaBIOS src/hw/pci_regs.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/pci_regs.h>`_。