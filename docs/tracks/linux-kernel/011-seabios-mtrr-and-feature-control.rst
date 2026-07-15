第十一章：SeaBIOS怎样设置MTRR并为后续CPU记录MSR写入？
===================================================

上一章的两个正常出口都会回到BSP上的 ``qemu_platform_setup()``：QEMU提供SMM时，
BSP已经完成SMBASE迁移；QEMU不提供SMM时，SeaBIOS已经跳过。两条路径的下一条调用
相同：

::

   mtrr_setup()
   → msr_feature_control_setup()
   → smp_setup()

本章处理前两项，停在 ``smp_setup()`` 之前。执行者仍是SeaBIOS MainThread，CPU仍是
BSP，普通执行环境为32位保护模式、分页关闭、IF=0；没有AP与BSP并发。MTRR和
``IA32_FEATURE_CONTROL`` 都是每个逻辑CPU的MSR状态，所以代码一边立即写BSP，
一边把相同的 ``index/value`` 序列留给下一章可能出现的AP重放。

能进入函数不等于一定改写MTRR
----------------------------

默认QEMU构建启用 ``CONFIG_MTRR_INIT``，但 ``mtrr_setup()`` 仍按运行时能力保留
三个返回门：

.. code-block:: c

   if (!CONFIG_MTRR_INIT)
       return;
   if (!(cpuid_features & CPUID_MTRR))
       return;
   if (!(cpuid_features & CPUID_MSR))
       return;

通过CPUID后，BSP读取 ``MSR_MTRRcap``：低8位是variable-range pair数量
``vcnt``，bit 8表示fixed-range MTRR可用。 ``vcnt==0`` 或fixed能力不存在时也直接
返回。当前固定条件没有唯一指定QEMU CPU model，因此正文不能只凭“x86-64”删除这些
分支。

只有全部检查通过，下面的写入才发生。源函数在这里没有执行 ``WBINVD``，也没有通过
CR0.CD关闭cache；它做的是先清 ``IA32_MTRR_DEF_TYPE``，完成寄存器序列，再重新启用
MTRR。不能把架构文档中更完整的多处理器更新协议当成这段SeaBIOS已经执行的步骤。

wrmsr_smp先改BSP，再尝试写入32项日志
-----------------------------------

所有实际写入都经过：

.. code-block:: c

   void wrmsr_smp(u32 index, u64 val)
   {
       wrmsr(index, val);
       if (smp_msr_count >= ARRAY_SIZE(smp_msr)) {
           warn_noalloc();
           return;
       }
       smp_msr[smp_msr_count].index = index;
       smp_msr[smp_msr_count].val = val;
       smp_msr_count++;
   }

顺序决定了溢出的真实语义： ``wrmsr()`` 总是先作用于当前BSP；32项静态
``smp_msr`` 数组已满时，SeaBIOS随后告警并停止记录该项，但不会撤销BSP写入，也不会
中止 ``mtrr_setup()``。所以这不是“容量检查失败，所有CPU都不写”，而是可能产生
“BSP继续前进，未来AP只重放前32项”的不一致。

关闭MTRR是日志中的第一项
-------------------------

成功路径第一项为：

.. code-block:: c

   wrmsr_smp(MSR_MTRRdefType, 0);

它清除 ``IA32_MTRR_DEF_TYPE`` 的默认类型与fixed/variable enable。BSP立即看到MTRR
关闭；相同写入占用重放表的一项。之后的AP若存在，会从这项开始按相同顺序重放。

低端1 MiB由11个fixed-range MSR描述
----------------------------------

SeaBIOS用一个 ``FIX64K_00000`` MSR覆盖0—512 KiB。64位值中的每个byte对应64 KiB；
只有 ``RamSize`` 到达该byte结尾时才写入类型6（WB），未到达的byte保持0（UC）。

第二个 ``FIX16K_80000`` 用八个16 KiB字段覆盖0x80000—0x9ffff，同样按
``RamSize`` 逐段置WB。 ``FIX16K_A0000`` 则无条件写0，使0xa0000—0xbffff为UC；
这一区间同时承载传统VGA aperture和芯片组控制的SMRAM视图，不能当普通write-back
RAM缓存。

最后八个 ``FIX4K_C0000`` 至 ``FIX4K_F8000`` 覆盖0xc0000—0xfffff。SeaBIOS把
仍落在 ``RamSize`` 内的4 KiB字段写成5（WP），其余保持UC。这里的MTRR类型与Q35
PAM地址译码是不同层：PAM决定访问落到ROM还是shadow RAM；MTRR决定CPU怎样缓存该
物理访问。

这部分一共写11个fixed-range MSR。连同开头关闭 ``DEF_TYPE`` 的一项，日志此时
已经使用12项。

variable pair先全部失效，再用pair 0覆盖PCI hole
-----------------------------------------------

SeaBIOS默认把物理地址宽度设为36；如果扩展CPUID最高leaf达到 ``0x80000008``，则用
该leaf EAX低8位替换。随后：

.. code-block:: c

   phys_mask = (1ULL << phys_bits) - 1;
   for (i = 0; i < vcnt; i++) {
       wrmsr_smp(MTRRphysBase_MSR(i), 0);
       wrmsr_smp(MTRRphysMask_MSR(i), 0);
   }

每个variable pair都先以base=0、mask=0失效，因此这里增加 ``2 * vcnt`` 项写入。
代码不读取并恢复此前的variable MTRR；它直接以自己的完整启动配置覆盖。

第008章已经由固定Q35 PCIEXBAR得到：

::

   PCIEXBAR base = 0xb0000000
   PCIEXBAR size = 0x10000000
   pcimem_start  = 0xc0000000

SeaBIOS再写variable pair 0：base带UC类型，mask覆盖从 ``pcimem_start`` 到4 GiB并
置valid bit。因此固定q35的实际UC范围是：

::

   0xc0000000—0xffffffff  (3 GiB—4 GiB)

``mtrr.c`` 中“3.5—4GB”的注释与这一固定变量值不一致；可执行表达式使用
``pcimem_start``，所以本书采用3—4 GiB。这个范围包含PCI/PCIe MMIO窗口、平台固定
MMIO与顶端保留映射，不只包含本轮实际分配的BAR。

最后重新启用并以WB作为默认类型
--------------------------------

pair 0的base/mask占两次写入。最后：

.. code-block:: c

   wrmsr_smp(MSR_MTRRdefType, 0xc00 | MTRR_MEMTYPE_WB);

bit 10启用fixed ranges，bit 11启用MTRR，低类型值6把未被特定range覆盖的地址设为
WB。能力完整且写入没有CPU异常时，BSP此时的基础类型为：

::

   RamSize内的低端RAM字段       WB
   0xa0000—0xbffff              UC
   RamSize内的0xc0000—0xfffff  WP
   0xc0000000—0xffffffff        UC
   未被特定range覆盖的地址      WB

高于4 GiB的普通RAM不落入本pair 0，沿用WB默认类型。操作系统以后仍需让PAT、页表属性
与MTRR组合保持一致；本章没有分页，也没有建立Linux映射。

MTRR成功路径实际需要15加2倍vcnt项
----------------------------------

把源码中的调用逐项计数：

::

   disable DEF_TYPE       1
   fixed-range MSR       11
   clear variable pairs  2 * vcnt
   program pair 0         2
   enable DEF_TYPE        1
   --------------------------------
   total                  15 + 2 * vcnt

如果 ``vcnt=8``，MTRR占31项；后面的FEATURE_CONTROL最多还能使用最后一项。如果
``vcnt>=9``，MTRR自身就超过32项。由于当前固定条件没有规定 ``MTRRcap.vcnt``，
不能断言静态数组一定够用。

溢出不会改变BSP已经写完的结果，但会截断AP模板。例如 ``vcnt=9`` 时，第33次调用是
最终重新启用 ``DEF_TYPE``：BSP会执行它，日志却没有空间记录；下一章的AP会重放到
pair 0为止，却不重新启用MTRR。更大的 ``vcnt`` 还会更早截断。这个边界必须在AP状态
中继续携带，不能笼统写成“每个CPU必然相同”。

FEATURE_CONTROL是否存在由QEMU CPU能力决定
-----------------------------------------

``mtrr_setup()`` 返回后，BSP调用 ``msr_feature_control_setup()``，从fw_cfg读取：

::

   etc/msr_feature_control

QEMU只在vCPU公布下列至少一种能力时创建该文件：VMX outside SMX、LMCE、SGX或
SGX Launch Control。它组合相应enable位并一并设置 ``FEATURE_CONTROL_LOCKED``；
没有任何功能位时直接不创建文件。

SeaBIOS用缺省值0加载该文件，只有非零时才执行：

.. code-block:: c

   wrmsr_smp(MSR_IA32_FEATURE_CONTROL, feature_control_bits);

因此固定CPU model未唯一化时有两条正常结果：文件缺失/值0，不写MSR也不增加日志；
文件非零，BSP写入带lock的QEMU策略，并尝试把它追加到同一个32项重放表。

若MTRR已经占满日志，这次FEATURE_CONTROL仍先写BSP，再告警且不记录。于是“BSP已锁
FEATURE_CONTROL”与“未来AP会得到同一lock值”也必须分开陈述。

本章结束状态
------------

共同状态：

* current executor：BSP上的SeaBIOS ``MainThread``；
* CPU/mode：BSP，32位保护模式，分页关闭、A20开启、IF=0；
* NMI/PIC：继承第010章，未改变；
* AP：尚未由SeaBIOS启动，没有MSR重放发生；
* ``smp_msr``：保存至多32个 ``index/value``，保持实际调用顺序；
* 溢出语义：BSP先写成功，超限项只是不进入AP模板；
* SMM：保持第010章的成功或跳过分支，不受本章改变；
* 固件表、设备驱动、GRUB与Linux：尚未进入。

若CPUID与 ``MTRRcap`` 满足全部门：

* BSP MTRR：按fixed ranges、variable pair 0和WB默认类型完成配置；
* q35 ``0xc0000000—0xffffffff``：UC；
* MTRR调用数： ``15 + 2 * vcnt``；
* 日志不超过32项时：完整MTRR序列可供AP重放；
* 日志超过32项时：BSP配置仍继续，AP模板被截断。

若任一MTRR能力门不满足：

* ``mtrr_setup()`` 返回，不改BSP MTRR，也不为MTRR增加日志项。

若QEMU发布非零 ``etc/msr_feature_control``：

* BSP写入带lock的 ``IA32_FEATURE_CONTROL``；
* 仅在日志尚有容量时，该项也可供AP重放。

否则本章不写 ``IA32_FEATURE_CONTROL``。

关键边界
--------

#. 默认构建启用MTRR初始化，不删除CPUID与 ``MTRRcap`` 的运行时返回分支。
#. 固定函数没有执行完整的cache-disable/flush协议；正文只记录它实际写的MSR序列。
#. ``pcimem_start`` 是固定Q35路径算出的3 GiB，不采用源码注释中的3.5 GiB泛称。
#. ``wrmsr_smp`` 先写BSP、后检查32项日志容量；溢出不是写入前拒绝。
#. MTRR成功路径需要 ``15 + 2 * vcnt`` 项，容量是否足够取决于未固定的CPU能力。
#. FEATURE_CONTROL文件与数值由QEMU vCPU能力决定，不是所有q35启动的固定常量。
#. 日志完整时AP可按原顺序重放；日志截断时不能宣称BSP/AP的MSR状态一致。

下一入口
--------

``msr_feature_control_setup()`` 返回后，BSP执行：

::

   qemu_platform_setup()
   → smp_setup()

下一章先读取 ``etc/max-cpus`` 与在场CPU数，再决定是否真的有AP执行
``entry_smp()``；本章只建立可能被重放的MSR模板。

资料
----

* `SeaBIOS固定提交：MTRR能力门与写入序列 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/mtrr.c#L36-L105>`_
* `SeaBIOS固定提交：wrmsr_smp容量与重放顺序 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/smp.c#L27-L50>`_
* `SeaBIOS固定提交：FEATURE_CONTROL读取与平台调用顺序 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/paravirt.c#L260-L299>`_
* `SeaBIOS固定提交：Q35 PCIEXBAR与pcimem_start <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/pciinit.c#L480-L503>`_
* `QEMU固定提交：FEATURE_CONTROL fw_cfg构造 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/fw_cfg.c#L176-L211>`_
* `Intel 64 and IA-32 Architectures Software Developer Manuals <https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html>`_
