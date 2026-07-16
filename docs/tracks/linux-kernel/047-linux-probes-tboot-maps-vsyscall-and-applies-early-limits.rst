第四十七章：Linux 怎样处理 tboot、vsyscall、early PCI quirk 与 CPU 上限？
============================================================================

第四十六章结束时，CPU0仍在 ``setup_arch``、IF=0，active CR3是 ``init_top_pgt``；CMA、
crashkernel、xDBC和KASAN已分别走完build/effective-policy条件路径。early ACPI只登记LAPIC地址，
full firmware CPU/IOAPIC enumeration仍未执行。当前入口是：

.. code-block:: c

   tboot_probe();

本章按fixed Linux 7.2-rc1继续到 ``acpi_boot_init()`` call前。它先检查boot protocol中的Intel
tboot shared-page identity，再按build/policy处理legacy x86-64 vsyscall ABI；随后x86-64跳过32-bit
APIC probe，用direct PCI config完成一轮受限quirk scan，并在firmware parser分配logical CPU IDs前
收紧possible-space上限。

fixed GRUB把未使用的 ``tboot_addr`` 留为0
------------------------------------------

GRUB第031章先清零 ``linux_params``，再只复制/改写已知setup-header与loader字段；本场景没有tboot
loader写 ``boot_params.tboot_addr``。因此 ``tboot_probe`` 的第一条guard：

.. code-block:: c

   if (!boot_params.tboot_addr)
       return;

在fixed普通GRUB启动中确定成立。CPU0不建立 ``FIX_TBOOT_BASE`` mapping，全局static ``tboot`` 保持
NULL， ``tboot_enabled()`` 为false。

这只排除“本次由tboot measured launch进入”，不改变TPM、IMA或以后安全子系统是否编入；它们不是
同一状态。

非0地址还要经过E820 point identity与shared-page内容校验
-------------------------------------------------------

fallback branch用于其他bootloader/tboot入口。源码注释要求valid page-aligned shared-page address，
但当前函数的实际guard只有nonzero以及：

.. code-block:: c

   e820__mapped_any(tboot_addr, tboot_addr, E820_TYPE_RESERVED)

它把同一个address同时作为overlap helper的start/end；按helper的 ``entry.addr>=end`` 与
``entry.end<=start`` predicates，只有address严格落在matching reserved entry内部才可命中，位于
entry起点也会失败。这既不是完整PAGE_SIZE range check，也没有显式验证alignment。通过后才把
physical address放进 ``FIX_TBOOT_BASE``，令 ``tboot`` 指向固定virtual slot。

``check_tboot_version`` 再比较16-byte ``TBOOT_UUID`` 并要求version至少5。任一失败都把global pointer
重新清为NULL；成功才保留tboot runtime state，供shutdown/S3/DMAR等协作。映射可读、E820 reserved
与内容确为tboot是三层不同判断。

``map_vsyscall`` 可能在build期就是no-op
-----------------------------------------

未编入 ``CONFIG_X86_VSYSCALL_EMULATION`` 时，arch header给 ``map_vsyscall`` inline empty function。
编入时fixed 7.2-rc1的build default只能是 ``XONLY`` 或 ``NONE``；early ``vsyscall=emulate|xonly|none``
可以改mode。fixed GRUB原始line没有该option，builtin line/config未知，所以不能指定当前mode。

这是legacy x86-64 fixed-address ABI，与现代vDSO不是同一机制；本次call也不会创建用户task或一个
普通per-mm ``mmap``。

EMULATE、XONLY与NONE有三种不同page-table结果
-----------------------------------------------

``EMULATE`` 才把linked ``__vsyscall_page`` 的physical address装入 ``VSYSCALL_PAGE`` fixmap，使用
``PAGE_KERNEL_VVAR``，并调用 ``set_vsyscall_pgtable_user_bits(swapper_pg_dir)``。后者在覆盖
``VSYSCALL_ADDR`` 的PGD/P4D/PUD/PMD逐级OR ``_PAGE_USER``，让user page walk能到达PTE；执行旧入口
后由fault/trap emulation提供 ``gettimeofday/time/getcpu`` 兼容语义。

``XONLY`` 不建立backing PTE，只把static ``gate_vma.vm_flags`` 设为 ``VM_EXEC``，由instruction fault
路径模拟； ``NONE`` 既不映射PTE，也令 ``get_gate_vma`` 返回NULL。三种mode最后都用
``BUILD_BUG_ON`` 保证fixmap计算地址与ABI ``VSYSCALL_ADDR`` 一致，这个检查是compile-time layout
约束，不是runtime fallback。

``gate_vma`` 只是固定ABI的描述对象
------------------------------------

enabled mode下 ``get_gate_vma`` 返回一个覆盖 ``[VSYSCALL_ADDR,VSYSCALL_ADDR+PAGE_SIZE)`` 的static
pseudo VMA，供core dump、ptrace/address checks描述 ``[vsyscall]``。它没有插入当前 ``init_task`` 的
VMA tree，更没有创建第一个userspace mm。IF仍为0，scheduler未运行。

x86-64的 ``x86_32_probe_apic`` 是inline空函数
-----------------------------------------------

下一条公共call只在 ``CONFIG_X86_LOCAL_APIC && CONFIG_X86_32`` 时有实现。fixed architecture是
x86-64，所以编译成no-op；它不会选择64-bit APIC driver，也不会探测/映射Local APIC。当前LAPIC
address/fixmap来自045的 ``register_lapic_address``，full topology仍留给048。

``early_quirks`` 使用direct PCI config做受限扫描
-------------------------------------------------

若 ``early_pci_allowed`` 为false，函数直接返回；ordinary q35 BIOS路径可用early PCI access时，从
bus 0扫描slot 0..31、function 0..7。读取class/vendor/device后匹配 ``early_qrk[]``；遇PCI bridge才
递归到其secondary bus，single-function device在function 0后停止。

这是“poor man's PCI discovery”：不创建 ``pci_dev``、不分配BAR、不绑定driver。fixed table只包含
NVIDIA/VIA bridge quirks、AMD K8 host HyperTransport、两个ATI SMBus、三个Intel remapping host
IDs、Intel VGA、Bay Trail host HPET disable和Apple Broadcom 4331 reset。它不是任意early PCI
fixup的总入口。

fixed q35 host/ICH9 core IDs本身不等于这些实体芯片组条目；默认/附加display与PCI devices又未由
完整QEMU CLI固定，所以当前可靠状态是“扫描并应用actual matches”，不宣称某条invasive quirk必然
发生。045已令 ``x86_apple_machine=false``，即使出现Broadcom 4331，Apple reset helper也返回。

firmware枚举前只收紧possible CPU编号空间
-------------------------------------------

``topology_apply_cmdline_limits_early`` 从当前 ``nr_cpu_ids`` 开始。此时048的MADT/MP processor
entries尚未解析，所以它限制的是parser未来可分配的logical ID capacity，不是已发现CPU集合。

fixed逻辑精确为：

.. code-block:: c

   possible = nr_cpu_ids;
   if (!setup_max_cpus || apic_is_disabled)
       possible = 1;
   possible = min(max_possible_cpus, possible);
   if (possible < nr_cpu_ids)
       set_nr_cpu_ids(possible);

``setup_max_cpus==0`` 对应 ``maxcpus=0``/``nosmp``， ``apic_is_disabled`` 可来自 ``nolapic``；
``max_possible_cpus`` 由 ``possible_cpus=N`` 设置，default是 ``NR_CPUS``。

正数 ``maxcpus=N`` 不在这个function中把possible capacity缩成N：它主要限制后面实际bring-up数量。
同样， ``nr_cpu_ids`` 可能已经受更早 ``nr_cpus=`` 等policy影响，本函数不会扩大它。fixed GRUB原始
line没有这些options，但builtin command line未知，所以保持conditional；普通无override q35路径
不在这里缩到1。

possible capacity、present、online与executing仍是四个状态
------------------------------------------------------

本章只可能修改 ``nr_cpu_ids`` 上限。 ``topology_init_possible_cpus`` 尚未根据firmware APIC IDs填
possible/present masks；即使上限大于1，也不证明存在第二个CPU。当前依旧只有CPU0 present/online/
active并执行 ``setup_arch``，没有per-CPU area、idle task、runqueue或INIT/SIPI for APs。

下一条 ``acpi_boot_init`` 才开始full MADT processor/IOAPIC parse，之后MP parser fallback与
``topology_init_possible_cpus`` 才把capacity变成实际possible set。

本章结束状态
------------

* current executor：CPU0上的 ``setup_arch``， ``acpi_boot_init()`` 尚未调用；
* CPU/mode：BSP/logical CPU0，x86-64 long mode，IF=0，无schedule/AP bring-up；
* tboot：fixed GRUB ``tboot_addr=0``，probe返回， ``tboot=NULL``；
* vsyscall：build no-op，或按effective EMULATE/XONLY/NONE完成fixed-ABI setup；具体mode未固定；
* vsyscall EMULATE：有PTE与upper-level user bits；XONLY：无PTE、gate executable；NONE：无gate；
* ``x86_32_probe_apic``：x86-64 no-op；
* early PCI quirks：early access有效时已扫描actual bus tree并应用table matches；
* q35/ICH9：没有因平台名被武断套入实体机quirk；
* ``nr_cpu_ids``：已应用zero-maxcpus/APIC-disabled/possible_cpus等early cap；actual value未固定；
* full MADT/MP processor entries：尚未解析；
* possible/present CPU topology：尚未由firmware结果重新建立；
* Local APIC：045已登记address；048的last-opportunity check尚未执行；
* IOAPIC：尚未full parse或映射。

关键边界
--------

#. fixed GRUB的tboot field来自zeroed params且无人改写，所以本次probe确定在zero guard返回。
#. nonzero tboot branch给E820 overlap helper传相同start/end，只能作严格内部point guard；它不验证
   整页、alignment或内容，UUID/version是后续边界。
#. ``map_vsyscall`` 可因build完全no-op；fixed build default是XONLY/NONE，EMULATE需early option选择。
#. EMULATE有PTE；XONLY刻意没有PTE，只保留executable gate/fault emulation语义。
#. gate VMA是static pseudo description，不是为 ``init_task`` 执行一次mmap。
#. x86-64 ``x86_32_probe_apic`` 无工作，不能记入Local APIC发现。
#. ``early_quirks`` 是limited direct-PCI table scan，不是完整PCI enumeration或所有PCI fixups。
#. q35 core IDs与table matches分开；未固定optional devices不能制造quirk结果。
#. early limit在firmware enumeration前缩 ``nr_cpu_ids`` capacity，不建立possible CPU set。
#. 只有 ``setup_max_cpus==0`` 在这里强制capacity=1；positive ``maxcpus=N`` 不是本函数的N上限。
#. possible、present、online与executing CPU identities不能互换。
#. 048从full ACPI/MADT开始，才首次枚举本场景的processor records。

下一入口
--------

第048章从：

.. code-block:: c

   acpi_boot_init();

开始。进入前early quirks与CPU capacity limit已生效，LAPIC address已登记；MADT processor、IOAPIC、
interrupt overrides和NMI entries尚未full parse。

资料
----

* `Linux 7.2-rc1固定提交：tboot到CPU limit调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L1215-L1228>`_；
* `Linux 7.2-rc1固定提交：tboot E820 point、fixmap与UUID/version校验 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/tboot.c#L35-L96>`_；
* `Linux 7.2-rc1固定提交：E820 mapped-any overlap predicates <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/e820.c#L71-L102>`_；
* `Linux 7.2-rc1固定提交：vsyscall mode、PTE与user-bit边界 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/vsyscall/vsyscall_64.c#L44-L75>`_；
* `Linux 7.2-rc1固定提交：map_vsyscall的EMULATE/XONLY差异 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/vsyscall/vsyscall_64.c#L365-L405>`_；
* `Linux 7.2-rc1固定提交：early direct-PCI quirk table与扫描 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/early-quirks.c#L699-L813>`_；
* `Linux 7.2-rc1固定提交：firmware parse前CPU capacity limit <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/cpu/topology.c#L411-L433>`_。
