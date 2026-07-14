第七十章：Linux 怎样运行全部 built-in initcall，并准备 initramfs 与 root filesystem？
===============================================================================

第六十九章结束时，允许范围内的 AP 已完成 bring-up，正式 workqueue、SMP scheduler topology、async framework、padata 和 page allocator late init 已建立。PID 1 仍在 ``kernel_init_freeable()`` 中以内核态执行。

接下来的控制流是：

.. code-block:: c

   do_basic_setup();
   kunit_run_all_tests();
   wait_for_initramfs();
   console_on_rootfs();

   if (init_eaccess("/init") != 0)
       prepare_namespace();

   integrity_load_keys();

本章追踪到 ``kernel_init_freeable()`` 返回。此时 built-in initcall 已全部执行，initramfs 的异步解包已经结束，PID 1 已准备好初始 console，并已在“运行 early userspace /init”与“由内核挂载 root= 设备”之间完成选择。

``do_basic_setup()`` 是什么边界
-----------------------------

源码对这一阶段的注释是：CPU subsystem、memory 和 process management 已经可以工作，现在开始执行真正的 subsystem 与 device 初始化。

``do_basic_setup()`` 的固定顺序是：

.. code-block:: c

   cpuset_init_smp();
   ksysfs_init();
   driver_init();
   init_irq_proc();
   do_ctors();
   do_initcalls();

它不只是“初始化驱动”。前四步建立设备和内核对象的公共框架，最后的 ``do_initcalls()`` 才按照链接顺序运行大量 built-in subsystem、filesystem 和 driver 初始化函数。

``cpuset_init_smp()`` 用最终 CPU mask 更新 cpuset
--------------------------------------------

前面的 ``cpuset_init()`` 已建立 root cpuset 的基本对象。当 AP online、scheduler domain 和 node mask 稳定后，``cpuset_init_smp()`` 把 root cpuset 的 effective CPU/memory mask 更新到真实 SMP 状态，并接通 scheduler domain rebuild 所需关系。

这一步不挂载 cgroupfs。它更新内核中的 cpuset controller 状态，使以后创建的 cgroup 和 task placement 能依据真实 online CPU topology 工作。

``ksysfs_init()`` 建立 ``/sys/kernel`` 对象基础
--------------------------------------------

``ksysfs_init()`` 在 sysfs/kobject 框架中登记 kernel kobject 与相关属性目录。后续 subsystem 可以在其下发布状态和控制节点。

此时只能说 sysfs 对象树具备对应节点。用户是否能从路径 ``/sys/kernel`` 看到它，还取决于 sysfs 是否被挂载到当前 VFS namespace。

``driver_init()`` 建立 Linux driver model
---------------------------------------

``driver_init()`` 依次建立：

.. code-block:: text

   backing-dev infrastructure
   → devtmpfs
   → devices
   → buses
   → classes
   → firmware
   → hypervisor
   → faux bus
   → device tree core
   → software nodes
   → platform bus
   → auxiliary bus
   → memory/node/CPU/container devices

从这里开始，内核有统一的 ``struct device``、``struct device_driver``、bus、class、firmware node 和 probe/bind 模型。

这仍不表示 AHCI、PCI、USB 等具体设备已经全部探测。driver core 是容器和匹配机制；具体 bus/driver 的 initcall 随后才注册和触发 probe。

``init_irq_proc()`` 准备 IRQ 的 proc 表示
---------------------------------------

该入口为 IRQ descriptor 建立 procfs 展示和 per-IRQ 节点基础，使后续可以形成 ``/proc/interrupts`` 与相关控制项。

这里依旧要区分：

.. code-block:: text

   proc entry 已登记
   ≠ procfs 已挂载
   ≠ 用户态现在已经读取该文件

``do_ctors()`` 执行内核链接进来的 constructor
-------------------------------------------

若配置启用 ``CONFIG_CONSTRUCTORS``，``do_ctors()`` 遍历链接器收集的 constructor function。它们属于 built-in kernel image 的静态构造入口，不是用户态 C++ constructor，也不是 loadable module init。

大多数普通 C 内核代码不依赖 constructor；该机制主要服务特定 compiler/runtime instrumentation 和内核组件。

initcall 是怎样分级的
-------------------

``do_initcalls()`` 按固定 level 遍历：

.. code-block:: text

   pure
   → core
   → postcore
   → arch
   → subsys
   → fs
   → device
   → late

每一级在链接时对应一段 ``__initcall`` section。内核不会在运行时按函数名排序，而是按 level 和 link order 依次执行。

在进入某一级之前，``do_initcall_level()`` 重新复制并解析 command line，只把属于当前 initcall level 的 module parameter 交给对应 built-in 代码。这样同一套参数机制可以在模块编进内核时仍按正确阶段生效。

``do_one_initcall()`` 如何约束初始化函数
-------------------------------------

每个 initcall 都通过 ``do_one_initcall()`` 调用。该包装器：

* 检查 initcall blacklist；
* 可记录开始、结束、返回值和耗时；
* 检查返回前后的 preempt count；
* 若函数错误地带着 IRQ disabled 返回，会记录警告并重新打开 IRQ；
* 把调用时序混入 latent entropy。

initcall 返回非零通常只记录失败，由对应 subsystem 决定影响范围。它不是统一 transaction；前面已成功初始化的组件不会因为后面某个 driver 失败而整体回滚。

各 level 大致建立什么
-------------------

level 名称表示依赖层次，不是绝对 subsystem 分类：

* ``pure/core/postcore``：最基础的内核服务、数据结构和早期 controller；
* ``arch``：架构与平台发现、PCI/ACPI 等 architecture-dependent 部分；
* ``subsys``：bus、network、ACPI bus、security 等大型 subsystem；
* ``fs``：VFS 上层、filesystem、rootfs/initramfs 相关入口；
* ``device``：大量 built-in hardware driver 注册与 probe；
* ``late``：必须等大多数 subsystem/device 可用后才执行的收尾。

具体函数属于哪个 level 由源码中的 ``core_initcall()``、``subsys_initcall()``、``device_initcall()`` 等宏决定。

固定 q35 机器在这里发生什么
-------------------------

随着 arch、subsys 和 device initcall 执行，固定平台会逐步注册并探测：

* ACPI interpreter 后续 bus/device scan；
* PCI host bridge 与 q35 PCI hierarchy；
* ICH9 southbridge 相关功能；
* AHCI controller 和 SATA disk；
* block layer、partition 和 filesystem driver；
* serial console、input、network 等编入内核的 driver。

实际可用范围取决于固定 kernel ``.config``。源码路径存在不代表 driver 一定 built-in；若 root disk 所需 driver 只存在于 initramfs module，必须由 early userspace 加载后设备才会出现。

``do_initcalls()`` 完成不等于所有异步 probe 已结束
----------------------------------------------

initcall 可以排队 async work，也可以触发 asynchronous device probe。``do_initcalls()`` 返回只表示所有同步 initcall function 已经被调用并返回。

PID 1 后面还会在 ``kernel_init()`` 中执行：

.. code-block:: c

   async_synchronize_full();

因此本章结束时不能声称全部 asynchronous initialization 已经完成。这里只能确认 built-in initcall 序列已走完。

KUnit 测试位于 initcall 之后
--------------------------

``kunit_run_all_tests()`` 在 basic setup 后运行内建 KUnit suite。未启用 KUnit 或没有内建 suite 时，该入口基本为空。

测试失败会按 KUnit 规则输出结果；是否阻止继续启动取决于测试和配置，不能笼统写成任何失败都会 panic。

initramfs 解包其实由 ``rootfs_initcall`` 启动
------------------------------------------

``populate_rootfs()`` 注册为 ``rootfs_initcall``。它在 initcall 阶段把真正工作排入专用 async domain：

.. code-block:: text

   populate_rootfs()
   → async_schedule_domain(do_populate_rootfs)
   → usermodehelper_enable()

``do_populate_rootfs()`` 首先解包 built-in initramfs，然后处理 GRUB 传入的外部 initramfs/initrd 区域。

对于有效 cpio initramfs：

.. code-block:: text

   compressed cpio archive
   → decompress
   → create directories/inodes/device nodes/symlinks
   → write files into rootfs

若输入不是 initramfs 且内核支持传统 block initrd，它可能保存为 ``/initrd.image``，留给后续 initrd 路径处理。

为什么这里再次调用 ``wait_for_initramfs()``
-----------------------------------------

由于 ``populate_rootfs()`` 默认可以异步解包，``do_initcalls()`` 返回时 archive 处理可能仍在进行。PID 1 显式调用：

.. code-block:: c

   wait_for_initramfs();

它等待 initramfs 专用 async domain 的 cookie 完成。返回后才能确认：

* built-in initramfs 已处理；
* GRUB 传入的 initramfs/initrd 已处理或报告错误；
* security initramfs population hook 已执行；
* 不需要保留的 initrd 物理内存已释放；
* 解包过程持有的延迟 file reference 已 flush。

这里的 ``rootfs`` 是内核早期挂载的 ramfs/tmpfs 根，不一定是最终 ``root=/dev/sda1`` 的 ext4 root filesystem。

``console_on_rootfs()`` 为 PID 1 建立 fd 0、1、2
--------------------------------------------

PID 1 接着打开：

.. code-block:: c

   /dev/console

成功后通过三次初始 fd 安装，让 stdin、stdout、stderr 都指向该 console。

``console_init()`` 在第六十三章已经让 console backend 可以输出 printk；本步骤解决的是未来用户态 PID 1 的 file descriptor 0、1、2。两者不是同一个阶段。

若 ``/dev/console`` 不存在或无法打开，内核记录警告。它不会在这里自动创建一个 shell。

分支一：rootfs 中存在可执行 ``/init``
------------------------------------

``ramdisk_execute_command`` 默认是：

.. code-block:: text

   /init

PID 1 调用 ``init_eaccess("/init")``。若文件存在且当前 credential 可以执行，``kernel_init_freeable()`` 不调用 ``prepare_namespace()``。

这表示 early userspace initramfs 路径被选中：

.. code-block:: text

   unpacked rootfs
   → /init exists
   → keep initramfs root as current root
   → later kernel_execve("/init")

``/init`` 通常负责加载 module、等待 storage、解密磁盘、组装 RAID/LVM，并最终通过 ``switch_root`` 或 ``pivot_root`` 切入真正 root filesystem。

当前固定 GRUB 配置传入了 initramfs 文件，因此这是一条重要可能路径；是否存在 ``/init`` 取决于该 archive 的实际内容，不能仅凭文件名断言。

分支二：没有可执行 ``/init``
---------------------------

若 ``/init`` 不可执行，源码执行：

.. code-block:: c

   ramdisk_execute_command = NULL;
   prepare_namespace();

若用户显式设置了 ``rdinit=`` 且不可访问，内核还会输出警告。

``prepare_namespace()`` 处理固定 ``root=/dev/sda1``
-------------------------------------------------

固定 command line 是：

.. code-block:: text

   root=/dev/sda1 ro console=ttyS0

``prepare_namespace()`` 的顺序是：

.. code-block:: text

   optional rootdelay
   → wait_for_device_probe()
   → md_run_setup()
   → parse root=/dev/sda1
   → initrd_load()
   → optional rootwait
   → mount_root()
   → devtmpfs_mount()
   → pivot into new root
   → detach old rootfs

``wait_for_device_probe()`` 等待已知 asynchronous probe 完成，避免 AHCI disk 尚未注册时立即判断 root device 不存在。

``parse_root_device()`` 把 ``/dev/sda1`` 解析为 ``dev_t``。若配置了 ``rootwait``，内核可以继续轮询 driver probe 与 block-device lookup；固定命令行未显式设置 ``rootwait``，因此不能假设会无限等待。

``mount_root()`` 根据 block device 和 ``rootfstype=``/自动探测选择 filesystem driver，并以 ``ro`` 要求挂载。成功后 ``prepare_namespace()`` 挂载 devtmpfs，pivot 到新 root，再 detach 旧的内存 rootfs。

如果 AHCI、SCSI disk、partition 或 ext4 支持未 built-in，且又没有可运行的 initramfs ``/init`` 负责加载 module，这条内核直挂路径会失败。固定主线的源码不能替代实际 ``.config`` 和 initramfs 内容。

两条 root 路径不能混成一步
-------------------------

本章结束时一定成立的是：

.. code-block:: text

   initramfs processing has completed
   PID 1 has checked /init

随后只能是二选一：

.. code-block:: text

   A. /init executable
      → initramfs remains current root
      → early userspace will mount/switch real root

   B. /init unavailable
      → prepare_namespace mounts root=/dev/sda1
      → kernel pivots to the block-device root

不能同时写成“内核已经 pivot 到 /dev/sda1，并且接下来运行 initramfs /init”。

``integrity_load_keys()`` 为什么放在 root 可用之后
----------------------------------------------

``kernel_init_freeable()`` 最后调用：

.. code-block:: c

   integrity_load_keys();

IMA/EVM 和其他 integrity 组件可能需要从当前 rootfs 读取 public key、keyring material 或 policy-related files。只有 root 内容已经确定后，加载这些资源才有明确来源。

未启用对应 integrity 配置时，该入口为空；启用时，实际加载结果取决于 key 文件、keyring 和 policy 配置。

本章结束时的系统状态
------------------

本章结束时：

* 当前主线执行者：PID 1 ``kernel_init()``；
* ``kernel_init_freeable()`` 已返回；
* PID 0 和各 online AP idle task 已运行；
* PID 2 kthreadd 与正式 workqueue 已可服务内核线程和 work；
* driver model 已建立；
* pure 至 late 的 built-in initcall 已全部调用；
* ACPI、PCI、block、filesystem 和 built-in driver 已按配置执行各自 initcall；
* initramfs async domain 已完成；
* PID 1 的 fd 0、1、2 已尝试连接 ``/dev/console``；
* root 路径已经完成选择：保留可执行 ``/init`` 的 initramfs，或由 ``prepare_namespace()`` 挂载并 pivot 到 ``root=/dev/sda1``；
* integrity key loading 已按配置执行；
* PID 1 仍在内核态，尚未 ``kernel_execve()``；
* 全局 asynchronous init work 尚需下一步 ``async_synchronize_full()`` 最终汇合；
* ``__init`` 内存尚未释放；
* ``system_state`` 仍未进入 ``SYSTEM_RUNNING``。

下一条控制流回到 ``kernel_init()``：

.. code-block:: c

   async_synchronize_full();
   system_state = SYSTEM_FREEING_INITMEM;
   free_initmem();
   mark_readonly();
   pti_finalize();
   system_state = SYSTEM_RUNNING;

随后 PID 1 才会尝试 exec ``/init``、``init=`` 指定程序或默认的 ``/sbin/init``。

资料
----

* `Linux 7.2-rc1 init/main.c：do_basic_setup、initcall levels、kernel_init_freeable 与 root 选择 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 7.2-rc1 drivers/base/init.c：driver_init 与 driver model core <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/base/init.c>`_
* `Linux 7.2-rc1 include/linux/init.h：initcall level 与 section macros <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/init.h>`_
* `Linux 7.2-rc1 init/initramfs.c：populate_rootfs、async unpack 与 wait_for_initramfs <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/initramfs.c>`_
* `Linux 7.2-rc1 init/do_mounts.c：prepare_namespace、root device lookup、mount 与 pivot <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/do_mounts.c>`_
* `Linux 7.2-rc1 security/integrity/iint.c：integrity initialization <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/security/integrity/iint.c>`_