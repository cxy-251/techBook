第四十章：Linux start_kernel 怎样建立最早的通用内核状态？
=============================================================

第三十九章结束时，BSP已经在正式kernel高地址映射中以 ``init_task`` 身份执行，IF和DF均为0；
formal BSS/brk已经清零，一般early IDT已经加载，全局 ``boot_params`` 与
``boot_command_line`` 也已从物理Z复制完成。当前入口是：

.. code-block:: c

   x86_64_start_reservations(Z)

本章按fixed Linux 7.2-rc1的真实调用顺序，从这个x86尾入口进入generic
``start_kernel()``，处理到 ``setup_arch(&command_line)`` 第一条语句尚未执行。内存图、
memblock和完整direct map仍留给后续章节。

有效 ``boot_params`` 使fallback copy不发生
---------------------------------------------

``x86_64_start_reservations`` 首先保留一道特殊入口防护：

.. code-block:: c

   if (!boot_params.hdr.version)
       copy_bootdata(__va(real_mode_data));

第三十九章已从GRUB交出的Z复制并sanitize了有效boot protocol header，当前
``hdr.version`` 非0，所以条件为假。CPU不会第二次读取Z，也不会第二次建立或撤销SME boot-data
mapping。参数 ``real_mode_data`` 仍携带物理数值Z，只是本批成功路径已经不再解引用它。

这道guard不能反推“Z会一直保留”。 ``copy_bootdata`` 的源码恰好说明old boot data不再需要且
不会被reserve；第041章检查early reservation时会看到，Z不在显式保留清单中。

ordinary PC先固定legacy平台假设
---------------------------------

下一条调用是：

.. code-block:: c

   x86_early_init_platform_quirks();

它先写入一组platform class默认值：i8042预期存在、RTC存在、允许warm reset、PnP BIOS可用，
并先把 ``reserve_bios_regions`` 清0。随后才按 ``boot_params.hdr.hardware_subarch`` 修正。

固定SeaBIOS加GRUB i386-pc路径交出的 ``hardware_subarch`` 是
``X86_SUBARCH_PC``。该case只把：

.. code-block:: c

   x86_platform.legacy.reserve_bios_regions = 1;

打开。它没有在这里扫描EBDA或立刻保留任何物理页，只是为第041章
``reserve_bios_regions()`` 选择成功分支。Xen会关闭PnP BIOS与RTC；Intel MID和CE4100还会声明
i8042缺席，但这些都不是当前PC路径。

函数末尾允许已经安装的 ``x86_platform.set_legacy_features`` callback再覆盖默认值。fixed
``x86_platform`` 的ordinary PC初值没有安装该callback，当前也不是先行改写它的Xen PV入口，
所以这里没有额外调用。这个null-check仍是源码边界，不能把“当前不调用”写成所有x86平台都没有
override。

第二个subarch switch也不进入Intel MID
-----------------------------------------

``x86_64_start_reservations`` 随后再次检查同一subarch：

.. code-block:: c

   switch (boot_params.hdr.hardware_subarch) {
   case X86_SUBARCH_INTEL_MID:
       x86_intel_mid_early_setup();
       break;
   default:
       break;
   }

当前PC值走 ``default``。因此没有把q35改造成Intel MID平台，也没有在这个入口提前改写timer、
PCI或legacy设备钩子。x86专用reservations wrapper至此只完成了platform class选择，随后以
``__noreturn`` 控制流调用：

.. code-block:: c

   start_kernel();

从这里开始，执行者仍是BSP/CPU0上的 ``init_task``，只是源码入口从x86汇合到所有体系结构共有的
``init/main.c``。

先给 ``init_task`` 栈写overflow sentinel
------------------------------------------

``start_kernel`` 第一条调用：

.. code-block:: c

   set_task_stack_end_magic(&init_task);

它用 ``end_of_stack(&init_task)`` 找到架构定义的栈末边界，写入 ``STACK_END_MAGIC``。这只建立
后续stack-overflow检查所需的哨兵；没有分配新栈、创建新task或切换当前栈。当前RSP仍位于第038章
选定的 ``init_task`` initial stack。

``smp_setup_processor_id`` 在fixed x86上是weak no-op
-----------------------------------------------------

下一行虽然写作：

.. code-block:: c

   smp_setup_processor_id();

但fixed树中没有x86 override，实际链接到 ``init/main.c`` 的weak空函数。它不读取APIC ID、
不重写per-CPU offset，也不在这里“选择CPU0”。当前logical CPU0、GSBASE和
``current_task=&init_task`` 已由第038章 ``common_startup_64`` 建立。

保留这个generic hook是为了允许其他architecture在同一通用入口更早固定processor ID；不能从
函数名给当前x86路径补出并不存在的runtime动作。

debug objects与build ID都受build条件约束
-----------------------------------------

接下来的两次调用是：

.. code-block:: c

   debug_objects_early_init();
   init_vmlinux_build_id();

启用 ``CONFIG_DEBUG_OBJECTS`` 时，前者初始化每个early object hash bucket的raw spinlock，并把
静态object pool节点接入boot pool。此时slab尚不可用，所以没有把它们转换成动态对象。关闭配置
时，header提供空inline。

``init_vmlinux_build_id`` 仅在stacktrace build-ID或vmcore-info相关配置需要时，解析运行中
``vmlinux`` 的notes并保存build ID；否则同样是空inline。build ID区分的是具体构建产物，不是把
``Linux 7.2-rc1`` release string再保存一次。最终 ``.config``、compiler与本地version suffix未被
固定，因此本书不制造一个具体build-ID值。

cgroup early阶段只建立root task最小归属
-----------------------------------------

随后：

.. code-block:: c

   cgroup_init_early();

启用cgroup时，它初始化default root，把 ``init_task.cgroups`` 以RCU指针指向静态
``init_css_set``，并只初始化声明 ``early_init`` 的controller。这里没有挂载cgroupfs、没有创建
用户可见目录，也没有遍历普通进程；关闭cgroup配置时调用退化为空stub。

当前仍只有CPU0执行，scheduler与普通RCU运行期尚未建立。这里的 ``RCU_INIT_POINTER`` 是发布
静态启动关系，不意味着已经发生一次grace period。

软件标志与hardware IF在同一处对齐
----------------------------------

``start_kernel`` 明确执行：

.. code-block:: c

   local_irq_disable();
   early_boot_irqs_disabled = true;

第039章入口已经继承IF=0，所以 ``local_irq_disable`` 在当前CPU上不会产生0→1→0的中断窗口；它
重新兑现generic入口的前置条件。紧接着的global boolean把这一阶段记录为“early boot要求IRQ
关闭”。

IDT已有early exception gates不等于普通maskable IRQ已经可用。IRQ descriptor、APIC mode、
timer与scheduler都尚未完成，本章没有执行 ``local_irq_enable``，也没有因为某个helper而发生
schedule。

``boot_cpu_init`` 发布CPU0的四种mask身份
-----------------------------------------

下一条真正建立global CPU topology状态的调用是：

.. code-block:: c

   boot_cpu_init();

它读取已经可用的 ``smp_processor_id()``，当前得到0，再依次把CPU0加入：

.. code-block:: text

   cpu_online_mask
   cpu_active_mask
   cpu_present_mask
   cpu_possible_mask

SMP build还写 ``__boot_cpu_id=0``。四个mask分别表达能否运行、能否参与调度迁移、是否实际存在、
以及内核是否允许该logical CPU存在；把BSP加入四者不等于发现或启动任何AP。AP的present/
possible信息与online bring-up要到后续firmware table和SMP阶段。

x86-64不建立hashed highmem page-address表
------------------------------------------

generic顺序接着调用 ``page_address_init()``。真正的函数只在
``HASHED_PAGE_VIRTUAL`` 架构初始化 ``page_address_htable`` 与其spinlock；当前x86-64不使用传统
32-bit HIGHMEM hashed page virtual机制，因此走空实现。此处既没有创建 ``struct page`` 数组，
也没有扩大direct map。

banner进入printk buffer不等于串口已经注册
-------------------------------------------

最后一条属于本章的调用是：

.. code-block:: c

   pr_notice("%s", linux_banner);

``linux_banner`` 包含release、compiler与build metadata。源码release固定为7.2-rc1，但最终
build字符串仍取决于未固定构建产物。 ``pr_notice`` 把记录送入当前printk路径；固定命令行中的
``console=ttyS0`` 尚未经过普通参数解析与console registration，所以不能仅凭这一行断言字符已经
从串口发出。

下一条源码就是：

.. code-block:: c

   setup_arch(&command_line);

本章在call发生前停止，不把x86 command line、E820或memblock状态提前写进generic前缀。

本章结束状态
------------

* current executor：Linux 7.2-rc1 ``start_kernel``，即将调用
  ``setup_arch(&command_line)``；callee第一条尚未执行；
* CPU/mode：BSP / logical CPU0，64-bit long mode，kernel high mapping；IF=0，DF=0；
* current task/stack： ``init_task`` / original initial stack；stack-end magic已写入；
* processor-ID hook：fixed x86 weak no-op；CPU0身份未被重选；
* platform class：ordinary ``X86_SUBARCH_PC``；legacy i8042/RTC/warm-reset/PnP BIOS默认有效，
  ``reserve_bios_regions=1``；
* CPU masks：CPU0为possible、present、online、active；没有AP被启动；
* early boot IRQ software state： ``early_boot_irqs_disabled=true``；
* debug objects/build ID/cgroup early状态：按build执行真实helper或空stub；
* general early IDT、early direct-map ``#PF`` 与CR3：继承第039章，未在本章替换；
* global ``boot_params`` 与bootloader command line：保持有效；Z未再次读取；
* E820、memblock RAM、 ``init_mm``、完整direct map：尚未建立本章后续状态；
* initramfs：仍只记录R/N，未relocate、未unpack；
* scheduler、maskable IRQ、AP与用户态：均未进入。

关键边界
--------

#. ``hdr.version`` guard当前为假；fallback存在不等于当前又copy一次Z。
#. PC quirk这里只设置 ``reserve_bios_regions`` policy，真正读取BDA/EBDA并reserve在041。
#. ordinary PC的 ``set_legacy_features`` 当前为NULL；Xen等平台仍可提供override。
#. fixed x86没有 ``smp_setup_processor_id`` override；CPU0来自038，不来自函数名暗示的探测。
#. debug objects、build ID与cgroup调用均有config stub边界，不得写成所有build都分配对象。
#. ``boot_cpu_init`` 只发布BSP mask身份，不发现或唤醒AP。
#. IDT可处理early exception与普通IRQ可用是两个边界；本章始终IF=0。
#. banner进入printk不保证 ``ttyS0`` 已输出；console参数仍未完成解析。
#. 本章不调用 ``setup_arch``，所以没有命令行override、E820导入或memblock RAM。

下一入口
--------

第041章从fixed ``init/main.c`` 的：

.. code-block:: c

   setup_arch(&command_line);

进入 ``arch/x86/kernel/setup.c``。开始前CPU0已加入四个CPU mask，IF仍为0；global
``boot_command_line`` 的bootloader字符串是
``BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0``，但compile-time
``CONFIG_CMDLINE`` 是否追加或覆盖尚未处理。

资料
----

* `Linux 7.2-rc1固定提交：x86_64_start_reservations <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/head64.c#L294-L310>`_；
* `Linux 7.2-rc1固定提交：ordinary PC platform quirks <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/platform-quirks.c#L9-L35>`_；
* `Linux 7.2-rc1固定提交：start_kernel最早前缀 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L971-L995>`_；
* `Linux 7.2-rc1固定提交：boot_cpu_init发布CPU masks <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cpu.c#L3153-L3169>`_；
* `Linux 7.2-rc1固定提交：init_task stack magic <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/fork.c#L906-L912>`_；
* `Linux 7.2-rc1固定提交：early cgroup root与init_task关系 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cgroup/cgroup.c#L6378-L6415>`_；
* `Linux 7.2-rc1固定提交：build-ID条件helper <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/lib/buildid.c#L393-L406>`_。
