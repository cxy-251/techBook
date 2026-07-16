第四十四章：Linux 怎样扩大启动日志并确认 initramfs 与 ACPI 表可以安全访问？
============================================================================

第四十三章结束时，CPU0仍在 ``setup_arch``、IF=0，active CR3已经切到
``swapper_pg_dir=init_top_pgt``；working E820中的RAM已经进入 ``memblock.memory``，direct map
覆盖范围记录在 ``pfn_mapped[]``，memblock allocation limit也扩大到 ``get_max_mapped()``。当前
入口是：

.. code-block:: c

   setup_log_buf(1);

本章按fixed Linux 7.2-rc1继续到 ``acpi_boot_table_init()`` 返回。它先按需把printk从静态ring
buffer迁到memblock动态buffer，再让GRUB传入的 ``/boot/initramfs.img`` 获得可持续访问的kernel
virtual range，最后给initrd内ACPI override和firmware ACPI initial tables建立早期保护。全程没有
unpack普通rootfs，也没有解析ACPI namespace或枚举设备。

``early=1`` 不宣布printk per-CPU data ready
----------------------------------------------

最早日志一直写入编进kernel image的 ``printk_rb_static``、 ``__log_buf`` 及其静态metadata。现在
memblock和direct map已经可用， ``setup_log_buf`` 才有条件申请更大对象；但参数 ``early=1`` 令它
跳过 ``set_percpu_data_ready()``。per-CPU area尚未建立，后面 ``start_kernel`` 还会以
``early=0`` 再调用一次。

函数先检查：

.. code-block:: c

   if (log_buf != __log_buf)
       return;
   if (!new_log_buf_len)
       return;

第一项使已经迁移过的dynamic buffer不会被重复替换；第二项表示若build与early options没有提出
更大长度，本次调用只保留static ring。因此“执行了call”不等于当前fixed build必然分配动态
buffer， ``new_log_buf_len`` 仍受未固定config与effective command line影响。

一次迁移要分配text、descriptor和info三类对象
------------------------------------------------

当 ``new_log_buf_len>0`` 时，函数用平均record大小换算descriptor数量：

.. code-block:: c

   new_descs_count = new_log_buf_len >> PRB_AVGBITS;

数量为0会报错并保留旧buffer。有效时依次通过memblock分配：

.. code-block:: text

   new_log_buf   new_log_buf_len bytes的record text storage
   new_descs     new_descs_count个struct prb_desc
   new_infos     new_descs_count个struct printk_info

这三块都必须位于第四十三章已经direct mapped且没有reserved的RAM内，才能立刻清零并交给
``prb_init``。text allocation失败时没有新对象；descriptor失败时释放text；info失败时先释放
descriptors再释放text。任何失败都不会把global ``prb`` 留在半初始化ring上。

旧record在指针发布前迁入新ring
--------------------------------

``prb_init(&printk_rb_dynamic,...)`` 建好目标ring后，函数初始化一个临时read record，保存local
IRQ state并遍历 ``printk_rb_static``。每条record由 ``add_to_rb`` 连同text与 ``printk_info`` 写入
新ring，而不是只拼接可见字符串；level/facility、timestamp、caller等metadata仍跟着record走。

随后才在同一local-IRQ-disabled window中完成：

.. code-block:: c

   log_buf_len = new_log_buf_len;
   log_buf = new_log_buf;
   new_log_buf_len = 0;
   ... copy static records ...
   prb = &printk_rb_dynamic;

``local_irq_save`` 阻止CPU0上的普通interrupt路径插入切换窗口，但NMI仍可写旧static ring。恢复
IRQ state后，源码从刚才的sequence继续扫一次旧ring，把切换前后迟到的NMI records补入；若最终
sequence仍落后于static ring的next sequence，才报告dropped message数量。

迁移只扩大保存能力，不完成console或调度器
---------------------------------------------

本次 ``setup_log_buf(1)`` 没有注册serial console、创建 ``/dev/kmsg``、启动printk kthread或打开
interrupt。GRUB字符串中的 ``console=ttyS0`` 仍要到后面的console init阶段才能决定正式输出设备。
当前变化只是static/dynamic ring选择及其memblock ownership；CPU0继续同步执行 ``setup_arch``。

BIOS入口跳过EFI secure-boot状态输出
------------------------------------

下一段源码只在 ``efi_enabled(EFI_BOOT)`` 时，根据 ``boot_params.secure_boot`` 输出enabled、disabled
或unknown。fixed入口是SeaBIOS加GRUB i386-pc，没有EFI boot flag，所以整个switch跳过；这里既不
把BIOS启动等同于“Secure Boot disabled”，也不在Linux中改变任何secure-boot policy。

``reserve_initrd`` 重新组合R/N并核对loader身份
------------------------------------------------

第四十一章的 ``early_reserve_initrd`` 已把GRUB提供的physical range保留，但当时尚不能保证整段
都在最终early direct map内。现在 ``reserve_initrd`` 再从boot params组合：

.. code-block:: text

   R = hdr.ramdisk_image | (ext_ramdisk_image << 32)
   N = hdr.ramdisk_size  | (ext_ramdisk_size  << 32)
   E = PAGE_ALIGN(R + N)

若boot params字段为0，fixed source还可退到 ``phys_initrd_start/size``；普通GRUB bzImage入口使用
header与extension字段。 ``type_of_loader==0``、 ``R==0`` 或 ``N==0`` 任一成立都会按“无bootloader
initrd”返回。当前场景已固定GRUB成功装入 ``/boot/initramfs.img``，所以R/N均非0并继续。

已完整direct mapped时只建立virtual identity
----------------------------------------------

函数先把 ``initrd_start`` 清0并检查：

.. code-block:: c

   pfn_range_is_mapped(PFN_DOWN(R), PFN_DOWN(E))

若 ``[R,E)`` 的所有PFN都落在第四十三章实际记录的mapped ranges内，fast path仅执行：

.. code-block:: c

   initrd_start = R + PAGE_OFFSET;
   initrd_end   = initrd_start + N;

没有copy，也没有释放旧reservation。 ``initrd_end`` 按真实N结束，而用于physical reservation与
PFN check的E向page boundary取整，这两个边界不能混为一谈。

虽然GRUB通常把R放在普通RAM，是否完整mapped还受effective builtin command line对E820的可能
限制及actual firmware layout影响；这些输入未固定，所以本书在此保留branch，而不宣称fixed
scenario必然走fast path。

未完整mapped时先搬到 ``max_pfn_mapped`` 以下
-----------------------------------------------

slow path调用 ``relocate_initrd``，用：

.. code-block:: c

   memblock_phys_alloc_range(PAGE_ALIGN(N), PAGE_SIZE,
                             0, PFN_PHYS(max_pfn_mapped));

取得一块确定可通过direct map访问的free RAM。分配失败直接panic；成功后先设置新的
``initrd_start/end``，再由 ``copy_from_early_mem`` 从旧physical R复制N bytes，copy失败同样panic。
返回 ``reserve_initrd`` 后才执行 ``memblock_phys_free(R,E-R)``，撤销旧initramfs reservation。

因此slow path的顺序是“新range已reserved并复制成功”在前，“旧range可再分配”在后；失败不会把
唯一有效archive提前释放。搬迁不改变cpio内容，也不等于解压。

ACPI table upgrade只扫描专用cpio目录
-------------------------------------

``acpi_table_upgrade`` 在相应build option启用时，从built-in initramfs或刚建立的
``[initrd_start,initrd_end)`` 选择data source；无data立即返回。它通过early cpio scanner寻找：

.. code-block:: text

   kernel/firmware/acpi/

最多收集 ``NR_ACPI_INITRD_TABLES=64`` 个受支持signature的文件，并逐个验证文件至少容纳header、
file size等于table length且checksum为0。一个普通 ``/boot/initramfs.img`` 是否含这些文件没有
固定清单，因此当前结果可能是0张override table。

如果找到有效table但kernel lockdown禁止ACPI override，函数记录后忽略；若允许，则在
``ACPI_TABLE_UPGRADE_MAX_PHYS`` 以下分配总buffer，同时用memblock与x86 arch reservation保护它，
再借early remap按chunk复制。这里仍没有展开initramfs其余文件、创建inode或执行 ``/init``。

``acpi_boot_table_init`` 只建立initial table list与保护
--------------------------------------------------------

下一条call先运行x86 ACPI DMI quirks。若config/effective command line/blacklist先前已经令
``acpi_disabled`` 为真，它直接返回。否则：

.. code-block:: c

   if (acpi_locate_initial_tables())
       disable_acpi();
   else
       acpi_reserve_initial_tables();

locate从firmware给出的root pointer定位RSDT/XSDT及子表，交给ACPICA early table manager验证和
登记。失败会明确禁用ACPI；成功才保护initial tables所占physical memory，防止后续allocator在
解析完成前复用ACPI reclaimable storage。

fixed QEMU q35/SeaBIOS会提供PC ACPI tables，但Linux build与effective options仍可禁用ACPI，所以
本章结束状态保持“成功SeaBIOS主线/禁用或定位失败分支”条件。即便成功，此处也没有执行AML、建立
namespace、枚举Local APIC/IOAPIC或读取SRAT memory affinity；那些属于后续不同入口。

本章结束状态
------------

* current executor：CPU0上的 ``setup_arch``，下一条是 ``vsmp_init()``；
* CPU/mode：BSP/logical CPU0，x86-64 long mode，IF=0，无schedule/AP bring-up；
* active CR3/direct map：继续是 ``init_top_pgt`` 与第四十三章的 ``pfn_mapped[]`` coverage；
* printk：若 ``new_log_buf_len>0`` 且三次allocation成功，已迁到dynamic ring；否则仍用static ring；
* printk per-CPU readiness/console：均未由本次early call完成；
* EFI secure-boot switch：fixed BIOS入口skip；
* initramfs physical identity：旧R/N继续reserved，或slow path复制成功后旧range已free；
* ``initrd_start/end``：有效initrd已指向完整direct-mapped archive；没有有效initrd时保持空；
* initramfs内容：未普通unpack；仅按build/data/policy条件扫描ACPI override目录；
* ACPI initial tables：成功SeaBIOS路径已定位并reserve；ACPI禁用/定位失败路径没有伪造table list；
* ACPI CPU/IOAPIC/SRAT/namespace：尚未在本章建立或完整解析；
* memblock：可能新增dynamic printk、relocated initrd或ACPI upgrade/table reservations。

关键边界
--------

#. ``setup_log_buf(1)`` 按需迁移； ``new_log_buf_len==0`` 是合法no-op，不宣布per-CPU data ready。
#. dynamic printk由text、descriptors和infos三块组成，partial failure按逆序释放。
#. local IRQ关闭不能排除NMI，所以发布dynamic ``prb`` 后还要补扫static ring。
#. ring buffer迁移不等于console、scheduler或printk thread初始化。
#. BIOS路径跳过EFI status switch，不能由此推导一个EFI secure-boot mode。
#. early reservation只防覆盖； ``reserve_initrd`` 才依据actual ``pfn_mapped[]`` 建立持续可访问地址。
#. initrd fast path不copy；slow path先分配/复制成功，再释放旧physical reservation。
#. ``initrd_end`` 用真实N，physical reserved end用 ``PAGE_ALIGN(R+N)``。
#. ACPI upgrade是专用cpio early scan，不是普通rootfs unpack。
#. initial ACPI table定位/保护与MADT、SRAT、AML namespace解析是不同阶段。
#. fixed firmware会提供ACPI不等于effective Linux配置保证启用ACPI。
#. 第045章入口前仍只有CPU0执行，possible CPU topology尚未由early MADT完整枚举。

下一入口
--------

第045章从：

.. code-block:: c

   vsmp_init();

开始，随后依次经过 ``io_delay_init``、 ``early_platform_quirks``、 ``early_acpi_boot_init``、early
MP/DT入口与 ``initmem_init``。进入前要特别保持：initial ACPI tables可以已定位，但full
``acpi_boot_init`` 尚未调用，early MADT阶段也尚未执行。

资料
----

* `Linux 7.2-rc1固定提交：setup_arch日志、initrd与ACPI调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L1157-L1179>`_；
* `Linux 7.2-rc1固定提交：setup_log_buf分配、迁移与失败回滚 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/printk/printk.c#L1149-L1270>`_；
* `Linux 7.2-rc1固定提交：initrd地址合并、快路径与搬迁 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L300-L399>`_；
* `Linux 7.2-rc1固定提交：initrd内ACPI table upgrade <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/acpi/tables.c#L421-L542>`_；
* `Linux 7.2-rc1固定提交：x86 initial ACPI table定位与reservation <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/acpi/boot.c#L1589-L1606>`_。
