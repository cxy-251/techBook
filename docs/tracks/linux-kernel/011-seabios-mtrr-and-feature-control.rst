第十一章：SeaBIOS 怎样规定物理地址的缓存类型并准备每个 CPU 的 MSR？
===================================================================

上一章结束时，SeaBIOS 已经完成 SMM 安装。控制流回到：

::

   qemu_platform_setup()

接下来的调用顺序是：

.. code-block:: c

   mtrr_setup();
   msr_feature_control_setup();
   smp_setup();

本章只处理前两项，停在 ``smp_setup()`` 即将开始的位置。

这两项都在写 Model-Specific Register，简称 MSR。MSR 是处理器内部的专用寄存器，不属于普通内存，也不属于
PCI 配置空间。软件使用 ``RDMSR`` 和 ``WRMSR`` 指令访问它们。

``mtrr_setup()`` 规定不同物理地址范围使用什么缓存类型；``msr_feature_control_setup()`` 根据 QEMU 提供的策略
写入 ``MSR_IA32_FEATURE_CONTROL``。它们还有一个共同要求：配置不能只作用于当前 BSP。稍后被唤醒的每个 AP
也必须得到相同设置。

本章沿下面的真实控制流前进：

::

   qemu_platform_setup()
   → mtrr_setup()
   → 检查 CPUID.MTRR 与 CPUID.MSR
   → 读取 IA32_MTRRCAP
   → 暂时关闭 MTRR
   → 配置 1 MiB 以下 fixed-range MTRR
   → 清空 variable-range MTRR
   → 把 q35 PCI MMIO hole 标成 UC
   → 重新启用 MTRR，默认类型设为 WB
   → msr_feature_control_setup()
   → 从 fw_cfg 读取 etc/msr_feature_control
   → 条件写入 IA32_FEATURE_CONTROL
   → 停在 smp_setup() 之前

本章固定使用：

::

   SeaBIOS repository: coreboot/seabios
   SeaBIOS commit:     c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   QEMU repository:    qemu/qemu
   QEMU commit:        a759542a2c62f0fd3b65f5a66ad9868201014669

缓存类型影响的是 CPU 怎样访问同一个物理地址
-------------------------------------------

CPU 看到一个物理地址时，不是所有范围都能按照普通 RAM 的方式缓存。

例如：

* 普通 DRAM 适合 ``Write-Back``，简称 ``WB``；
* PCI MMIO 寄存器通常必须是 ``Uncacheable``，简称 ``UC``；
* 固件 ROM 区可以使用 ``Write-Protect``，简称 ``WP``；
* VGA legacy aperture ``0xa0000-0xbffff`` 也不能被当成普通可回写 RAM。

如果把设备寄存器误标为 WB，CPU 可能把写操作暂存在 cache 中、合并写入或改变可见顺序。软件以为自己已经向设备
发送命令，设备实际上可能还没有看到那次写入。

如果把普通 DRAM 全部标成 UC，功能通常仍可能正确，性能会急剧下降，因为大量读写无法使用正常 cache 路径。

MTRR 是页表之外的物理内存类型来源
--------------------------------

MTRR 的全名是 Memory Type Range Registers。

Linux 以后还会通过页表项中的 PCD、PWT、PAT 等机制控制缓存属性。当前 SeaBIOS 尚未开启分页，所以这里不存在
页表属性。MTRR 直接依据物理地址范围决定基础内存类型。

因此当前关系是：

::

   CPU 发出物理地址访问
   → MTRR 判断该地址属于哪种内存类型
   → cache 和总线逻辑按该类型处理

Linux 接管后会重新建立自己的页表，并在 MTRR、PAT 和页表属性之间进行一致性管理。SeaBIOS 当前建立的是操作系统
启动前必须合理工作的固件环境。

mtrr_setup 先确认处理器真的支持 MTRR 和 MSR
-------------------------------------------

``mtrr_setup()`` 的第一层判断来自编译配置：

.. code-block:: c

   if (!CONFIG_MTRR_INIT)
       return;

随后读取 ``CPUID.01H:EDX``，检查两个能力位：

``CPUID_MTRR``
   处理器实现 MTRR。

``CPUID_MSR``
   处理器实现 ``RDMSR`` 和 ``WRMSR``。

只有两者同时存在，SeaBIOS 才继续。

接着读取：

::

   IA32_MTRRCAP = MSR 0x000000fe

低 8 位给出 variable-range MTRR 的数量 ``vcnt``，bit 8 表示 fixed-range MTRR 是否存在。当前代码要求两者都存在：

.. code-block:: c

   int vcnt = mtrr_cap & 0xff;
   int fix  = mtrr_cap & 0x100;

   if (!vcnt || !fix)
       return;

SeaBIOS 不假设所有 x86 CPU 都拥有相同数量的 variable MTRR，而是读取处理器自己报告的能力。

为什么修改前先关闭 MTRR
----------------------

第一条实际写入是：

.. code-block:: c

   wrmsr_smp(MSR_MTRRdefType, 0);

``IA32_MTRR_DEF_TYPE`` 位于 MSR ``0x2ff``。写 0 会暂时关闭 fixed 与 variable MTRR，并把默认类型字段清零。

修改 MTRR 时，处理器架构通常还要求软件妥善处理 cache、并发 CPU 和执行环境。SeaBIOS 当前仍只让 BSP 执行主流程，
其他 AP 尚未被唤醒；在这个受控启动阶段，它先关闭 MTRR，写完整套寄存器，再一次性重新启用。

这里调用的不是普通 ``wrmsr()``，而是 ``wrmsr_smp()``。这个区别会在本章后半部分展开。

1 MiB 以下为什么使用 fixed-range MTRR
------------------------------------

传统 PC 的第一个 1 MiB 不是一种均匀用途：

::

   0x00000 - 0x7ffff   低端 RAM
   0x80000 - 0x9ffff   低端 RAM / EBDA 附近
   0xa0000 - 0xbffff   VGA legacy aperture / SMRAM 相关窗口
   0xc0000 - 0xfffff   Option ROM 与 BIOS 区

fixed-range MTRR 专门精细描述这 1 MiB。它使用不同粒度：

::

   0x00000 - 0x7ffff   8 × 64 KiB
   0x80000 - 0x9ffff   8 × 16 KiB
   0xa0000 - 0xbffff   8 × 16 KiB
   0xc0000 - 0xfffff  64 × 4 KiB

一个 64 位 fixed-range MSR 内含 8 个 8 位类型字段。每个字节描述一个连续子区间。

0 到 512 KiB 被标为 WB
---------------------

SeaBIOS 先构造 ``IA32_MTRR_FIX64K_00000``：

.. code-block:: c

   for (i = 0; i < 8; i++)
       if (RamSize >= 65536 * (i + 1))
           u.valb[i] = MTRR_MEMTYPE_WB;

8 个字节分别对应：

::

   byte 0 → 0x00000-0x0ffff
   byte 1 → 0x10000-0x1ffff
   ...
   byte 7 → 0x70000-0x7ffff

只要对应范围落在 ``RamSize`` 内，就写入类型值 ``6``，即 WB。

当前 q35 虚拟机显然拥有远大于 512 KiB 的 RAM，因此这些字段通常全部成为 WB。源码仍保留按 ``RamSize`` 判断，
避免把并不存在的地址范围无条件标成普通 RAM。

512 KiB 到 640 KiB 继续按 16 KiB 标为 WB
---------------------------------------

接下来配置 ``IA32_MTRR_FIX16K_80000``：

.. code-block:: c

   if (RamSize >= 0x80000 + 16384 * (i + 1))
       u.valb[i] = MTRR_MEMTYPE_WB;

它覆盖：

::

   0x80000 - 0x9ffff

这一段仍属于低端内存，里面可能包含 EBDA 以及前面 SeaBIOS 的低端分配对象。对当前平台，它继续使用 WB。

0xa0000 到 0xbffff 被明确设为 UC
--------------------------------

SeaBIOS 对 ``IA32_MTRR_FIX16K_A0000`` 直接写 0：

.. code-block:: c

   wrmsr_smp(MSR_MTRRfix16K_A0000, 0);

MTRR 类型 0 就是 UC，因此整个：

::

   0xa0000 - 0xbffff

都按不可缓存方式访问。

这个范围具有多重历史用途：VGA legacy aperture 位于这里；上一章中 q35 还通过 SMRAM 映射机制让 ``0xa0000``
区域在 SMM 与普通执行环境中呈现不同内容。将它设为 UC 可以避免普通 cache 行掩盖这种设备或芯片组控制的映射变化。

0xc0000 到 0xfffff 使用 WP
-------------------------

最后 256 KiB 由 8 个 fixed-range MSR 描述，每个 MSR 管理 32 KiB，每个字节管理 4 KiB。

SeaBIOS 对存在的范围写入：

::

   MTRR_MEMTYPE_WP = 5

WP 表示读取可以缓存，处理器写入不会按照普通可回写内存处理。这适合 Option ROM 与 BIOS 映射：代码和静态数据经常
被读取执行，正常情况下不应把它当作普通可写 RAM。

注意，前面章节中 q35 PAM 可以临时把 BIOS shadow 区切换为可写 RAM。PAM 控制的是芯片组地址映射；MTRR 控制的是
CPU cache 类型。两者描述不同层面，不能互相替代。

variable MTRR 先全部清零
----------------------

fixed-range 配完后，SeaBIOS 读取 ``CPUID.80000008H:EAX`` 的低 8 位，得到处理器支持的物理地址位数。没有该 CPUID
leaf 时，代码回退到 36 位。

然后构造：

.. code-block:: c

   phys_mask = (1ULL << phys_bits) - 1;

接着把每一组 variable MTRR 的 base 和 mask 都写 0：

.. code-block:: c

   for (i = 0; i < vcnt; i++) {
       wrmsr_smp(MTRRphysBase_MSR(i), 0);
       wrmsr_smp(MTRRphysMask_MSR(i), 0);
   }

每组 variable MTRR 使用两个 MSR：

``IA32_MTRR_PHYSBASEn``
   保存基址和内存类型。

``IA32_MTRR_PHYSMASKn``
   保存地址 mask，并用 bit 11 表示该范围有效。

先清空全部组，可以避免继承虚拟 CPU 初始状态中无法确认的旧范围。

q35 的 PCI hole 从 0xc0000000 开始
--------------------------------

上一章已经得到：

::

   pcimem_start = 0xc0000000
   pcimem_end   = 0xfec00000

SeaBIOS 使用 variable MTRR 0，把从 ``pcimem_start`` 到 4 GiB 的整个区域设为 UC：

.. code-block:: c

   wrmsr_smp(MTRRphysBase_MSR(0),
             pcimem_start | MTRR_MEMTYPE_UC);

   wrmsr_smp(MTRRphysMask_MSR(0),
             (-((1ULL << 32) - pcimem_start) & phys_mask) | 0x800);

对固定 q35 路径：

::

   base = 0xc0000000
   size = 0x100000000 - 0xc0000000
        = 0x40000000
        = 1 GiB

所以实际被 variable MTRR 覆盖的是：

::

   0xc0000000 - 0xffffffff

SeaBIOS 源码注释写着 ``Mark 3.5-4GB as UC``，那是历史性的概括。当前固定 q35 路径的 ``pcimem_start`` 是
``0xc0000000``，也就是 3 GiB；本书以实际变量值为准，不能把注释中的 3.5 GiB 直接套到当前平台。

为什么范围扩大到 4 GiB，而不只标实际 BAR
--------------------------------------

``0xc0000000-0xffffffff`` 不只有本轮分配出来的 endpoint BAR。它还包含或可能包含：

* PCI/PCIe MMIO window；
* IOAPIC、local APIC 等固定平台 MMIO；
* BIOS 顶部映射；
* 芯片组保留范围；
* 未分配但不应被当作 DRAM 缓存的地址洞。

把整个 PCI hole 设为 UC，比逐个追踪当前 BAR 更稳妥。默认 WB 只应用于没有被这个 UC variable range 覆盖的地址。

重新启用 MTRR，并把默认类型设为 WB
---------------------------------

最后写回：

.. code-block:: c

   wrmsr_smp(MSR_MTRRdefType,
             0xc00 | MTRR_MEMTYPE_WB);

``0xc00`` 包含两个关键使能位：

* bit 10：fixed-range MTRR enable；
* bit 11：MTRR enable。

低类型字段写入 ``6``，把未被其他 MTRR 特别覆盖的物理范围默认设成 WB。

因此完成后的基础规则可以概括为：

::

   普通 RAM                    → WB
   0xa0000-0xbffff             → UC
   0xc0000-0xfffff             → WP
   0xc0000000-0xffffffff       → UC

高于 4 GiB 的普通 RAM没有落入这个 PCI-hole UC 范围，因默认类型为 WB，仍按正常可缓存内存访问。高位 PCI BAR 的
最终属性以后还需要操作系统结合 MTRR 与 PAT 正确映射。

wrmsr_smp 为什么既写寄存器又保存一份记录
--------------------------------------

``mtrr_setup()`` 的每次写入都经过：

.. code-block:: c

   void wrmsr_smp(u32 index, u64 val)
   {
       wrmsr(index, val);
       smp_msr[smp_msr_count].index = index;
       smp_msr[smp_msr_count].val = val;
       smp_msr_count++;
   }

第一行 ``wrmsr()`` 立即修改当前 BSP。

后面三行把相同的 ``MSR index + value`` 顺序保存到最多 32 项的 ``smp_msr`` 数组。

MSR 通常是每个逻辑处理器各自拥有的状态。BSP 写了 MTRR，不表示尚未运行的 AP 自动拥有相同设置。因此 SeaBIOS
先生成一份需要重放的 MSR 写入日志：

::

   BSP 现在执行 WRMSR
   +
   保存 index/value
   → AP 醒来后逐项执行相同 WRMSR

这也是为什么 ``mtrr_setup()`` 必须在 ``smp_setup()`` 之前：AP 被唤醒时，完整的 MTRR 写入序列已经准备好了。

MSR 写入顺序也被完整保留
----------------------

记录的不只是最终值，还包括先关闭、逐项配置、再重新启用的顺序：

::

   IA32_MTRR_DEF_TYPE = 0
   → fixed MTRR
   → variable base/mask 清零
   → PCI hole UC range
   → IA32_MTRR_DEF_TYPE = enable + WB

AP 之后调用 ``smp_write_msrs()`` 时会按数组顺序重放。这样 AP 不会先启用一套尚未写完整的 MTRR。

数组只有 32 项。如果写入数超过数组容量，SeaBIOS 会报告分配警告，当前固定配置的 MTRR 与 feature-control 写入数量
必须落在这一实现限制内。

IA32_FEATURE_CONTROL 的策略来自 QEMU
-----------------------------------

``mtrr_setup()`` 返回后执行：

.. code-block:: c

   msr_feature_control_setup();

SeaBIOS 自己不根据 CPUID 临时拼出位值，而是读取 fw_cfg 文件：

::

   etc/msr_feature_control

.. code-block:: c

   u64 feature_control_bits =
       romfile_loadint("etc/msr_feature_control", 0);

   if (feature_control_bits)
       wrmsr_smp(MSR_IA32_FEATURE_CONTROL,
                 feature_control_bits);

``MSR_IA32_FEATURE_CONTROL`` 的编号是：

::

   0x0000003a

如果 QEMU 没有提供该文件，或者值为 0，SeaBIOS不写这个 MSR。

QEMU 怎样生成这份值
------------------

当前参考 QEMU 源码中的 ``fw_cfg_build_feature_control()`` 会检查虚拟 CPU 暴露的能力，并按需加入：

* VMX outside SMX enable；
* Local Machine Check Exception，简称 LMCE；
* SGX enable；
* SGX Launch Control enable。

只要存在任一功能位，QEMU 还会加入 ``FEATURE_CONTROL_LOCKED``，然后把 64 位值发布为：

::

   etc/msr_feature_control

这意味着策略分工是：

::

   QEMU 根据虚拟 CPU 型号和功能决定允许哪些位
   → fw_cfg 把位图交给 SeaBIOS
   → SeaBIOS 写入每个 CPU 的 IA32_FEATURE_CONTROL

本书不假定所有 q35 启动都得到同一个固定数值。数值取决于虚拟 CPU 配置，例如是否暴露 VMX、SGX 或 LMCE。

LOCK 位为什么重要
----------------

``IA32_FEATURE_CONTROL`` 中的 lock bit 一旦设置，通常在 CPU 复位前不能再修改受控字段。

因此这是固件阶段的安全边界：操作系统看到的不只是“某功能是否由 CPUID 宣布”，还受到固件已经锁定的 feature-control
策略约束。

SeaBIOS 使用 ``wrmsr_smp()`` 写入该值，因此：

* BSP 立即得到 feature-control 设置；
* 写入动作被追加到 ``smp_msr`` 日志；
* 后续每个 AP 会获得同样的位图和 lock 状态。

如果只设置 BSP，系统不同 CPU 对 VMX、SGX 或 LMCE 的可用状态可能不一致，这是多处理器启动不能接受的。

当前还没有真正唤醒其他 CPU
-------------------------

到本章结束，SeaBIOS 已经准备好 AP 所需的 MSR 模板，但 ``smp_setup()`` 尚未调用。

当前发生的是：

::

   BSP 配置自己的 MTRR
   → BSP 条件配置 IA32_FEATURE_CONTROL
   → 保存所有需要 AP 重放的 WRMSR 序列

尚未发生的是：

::

   local APIC 启用
   → INIT/SIPI 广播
   → AP 从 0x10000 启动
   → entry_smp
   → handle_smp
   → AP 重放 MSR

这些属于下一章。

第十一章结束时的机器状态
----------------------

控制权目前走过：

::

   qemu_platform_setup()
   → smm_setup() 返回
   → mtrr_setup()
   → 检查 MTRR/MSR 能力
   → 暂时关闭 MTRR
   → 低端 RAM fixed range = WB
   → 0xa0000-0xbffff = UC
   → 0xc0000-0xfffff = WP
   → 清空 variable MTRR
   → 0xc0000000-0xffffffff = UC
   → 默认内存类型 = WB
   → 重新启用 fixed/variable MTRR
   → msr_feature_control_setup()
   → 条件读取 etc/msr_feature_control
   → 条件写 IA32_FEATURE_CONTROL

此刻：

* 当前执行者：SeaBIOS ``qemu_platform_setup()``；
* 当前 CPU：BSP；
* 普通执行模式：32 位保护模式；
* 分页：关闭；
* BSP MTRR：已经配置；
* 普通 RAM 默认缓存类型：WB；
* ``0xa0000-0xbffff``：UC；
* ``0xc0000-0xfffff``：WP；
* q35 3-4 GiB PCI hole：UC；
* ``IA32_FEATURE_CONTROL``：在 QEMU提供非零策略时已写入并锁定；
* ``smp_msr``：已经保存 AP 需要重放的 MTRR 与 feature-control 写入序列；
* AP：尚未被 SeaBIOS 唤醒；
* ACPI、SMBIOS、MP table：尚未建立；
* 设备驱动和启动介质探测：尚未开始；
* GRUB：尚未被读取或执行；
* Linux：尚未装入内存。

下一条调用是：

.. code-block:: c

   smp_setup();

下一章将从 BSP 的 local APIC 开始，解释 INIT/SIPI 广播、``0x10000`` 启动跳板、AP 之间共享栈的锁、APIC ID
记录，以及每个 AP 怎样重放本章保存的 MSR 序列。

资料
----

* `SeaBIOS src/fw/mtrr.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/mtrr.c>`_；
* `SeaBIOS src/fw/smp.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/smp.c>`_；
* `SeaBIOS src/fw/paravirt.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/paravirt.c>`_；
* `SeaBIOS src/x86.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/x86.h>`_；
* `QEMU hw/i386/fw_cfg.c <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/fw_cfg.c>`_；
* `Intel 64 and IA-32 Architectures Software Developer Manuals <https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html>`_。