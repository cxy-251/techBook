第二十一章：SeaBIOS怎样处理BCV并把固定启动盘映射成BIOS 0x80？
=================================================================

第020章结束时，BSP上的SeaBIOS ``MainThread`` 已从 ``optionrom_setup()`` 返回。它仍在
32位保护模式、分页关闭且自身IF=0的POST主流程中， ``have_threads=false``。固定
``BootList`` 已按priority排成：

::

   AHCI port 0 hard disk  priority 101
   iPXE BEV               priority 9999

当前没有BCV。BDA ``hdcount=0``， ``IDMap[EXTTYPE_HD]`` 为空；iPXE BEV只登记了vector，
也尚未执行。 ``maininit()`` 接下来连续调用：

.. code-block:: c

   interactive_bootmenu();
   wait_threads();
   prepareboot();

本章沿固定“没有按键输入”的启动主线追到 ``prepareboot()`` 返回。用户选择、附加BCV、
CD和HALT仍保留为明确条件分支，不混入固定出口。

默认菜单等待不会直接启动任何设备
------------------------------

``interactive_bootmenu()`` 先确认 ``CONFIG_BOOTMENU``，再读取
``etc/show-boot-menu``。固定没有override，默认值1使菜单提示启用；值2才有“只有一个启动
项且无TPM时跳过提示”的特殊分支，而固定BootList已有硬盘与iPXE两个条目，也不满足
单项条件。

SeaBIOS继续读取：

::

   etc/boot-menu-wait = 2500 ms
   etc/boot-menu-key  = scan code 1 (ESC)

MainThread先用INT 16h清空已有按键，再显示默认 ``Press ESC for boot menu``，等待最多
2500 ms。INT 16h调用使用16位寄存器帧与IF=1；当BDA keyboard ring为空时，等待路径可经
``yield_toirq`` 短暂 ``sti; hlt; cli``，让PIT/keyboard等硬件IRQ唤醒BSP。控制返回
32位MainThread后，IF仍为0。

固定主线没有按键， ``get_keystroke`` 返回-1，与ESC scan code不等，菜单函数立即返回。
它没有读磁盘、调用iPXE、执行BCV或修改BootList。

用户分支只改变BootList头部
-------------------------

如果用户按ESC，函数会先在菜单内调用一次 ``wait_threads()``，再按当前BootList打印
AHCI硬盘与iPXE。选中某项后只做：

.. code-block:: c

   hlist_del(&boot->node);
   boot->priority = 0;
   hlist_add_head(&boot->node, &BootList);

所以显式选择iPXE会让它成为后面最终启动序列的第一项，但仍不在菜单函数内执行。按ESC
退出二级菜单则保持原顺序。本章固定无输入路径不进入这些分支。

maininit的第二次wait在固定路径不迭代
----------------------------------

菜单返回后 ``maininit()`` 无条件调用 ``wait_threads()``。第019章的第一次barrier已使
PS/2和六个AHCI worker全部退出，第020章的Option ROM调用也没有创建SeaBIOS
``run_thread`` worker；因此固定 ``have_threads=false``，while循环一次都不执行。

这条barrier仍有配置意义：若 ``threads_during_optionroms()=true``，设备初始化会在VGA
之前启动而不经过第019章那个同步barrier，线程可在Option ROM阶段通过preemption/yield
继续推进，最终必须在这里收口。固定配置为false时，不能把第二次wait虚构成又完成一轮
AHCI探测。

prepareboot先经过固定无TPM路径
-----------------------------

MainThread进入：

.. code-block:: c

   void prepareboot(void)
   {
       tpm_prepboot();
       bcv_prepboot();
       cdrom_prepboot();
       pmm_prepboot();
       malloc_prepboot();
       e820_prepboot();
       HaveRunPost = 2;
       BiosChecksum -= checksum((u8*)BUILD_BIOS_ADDR,
                                BUILD_BIOS_SIZE);
   }

第016章已证明固定机器没有TPM2/TCPA table， ``TPM_version`` 没有进入1.2或2.0分支，
``TPM_working=0``。因此 ``tpm_prepboot`` 不发physical-presence或TPM2 command；
末尾action/separator helpers也因TPM不工作而不建log、不扩PCR。下一条真实有状态变化的
调用是 ``bcv_prepboot()``。

bcv_prepboot不会销毁或转换BootList
--------------------------------

``BootList`` 是POST期排序链表； ``BEV[20]`` 是之后 ``do_boot()`` 消费的固定数组。
``bcv_prepboot`` 遍历前者、填充后者，并映射SeaBIOS内建drive，但不会删除链表条目。
所以“把BootList转换成BEV数组”若暗示源链表消失，就不符合源码；准确关系是：

::

   BootList remains allocated
   + map selected drive_s objects into IDMap
   + append boot actions into separate BEV[]

``BEV[]`` 这个变量名也不表示数组只装PnP BEV。它还容纳generic floppy、hard disk、
CD、CBFS、HALT等类型。

固定bootorder没有HALT
---------------------

函数先用 ``find_prio("HALT")`` 查fw_cfg bootorder。固定QEMU使用old-style CMOS ``cad``，
没有HALT path，返回-1，不增加 ``IPL_TYPE_HALT``。显式per-device bootorder含HALT时，
SeaBIOS才按该priority插入一个策略项；它不是硬件设备。

固定第一项直接映射AHCI drive_s
-----------------------------

遍历的第一项是 ``IPL_TYPE_HARDDISK``，因此：

.. code-block:: c

   map_hd_drive(pos->drive);
   add_bev(IPL_TYPE_HARDDISK, 0);

``bda_init()`` 在POST开始已清零整个BDA，所以进入本章时 ``hdcount=0``。固定也没有较早的
hard-disk条目或BCV改变它。 ``map_hd_drive()`` 先保存：

::

   hdid = bda->hdcount = 0

``add_drive`` 检查 ``BUILD_MAX_EXTDRIVE`` 上限后执行：

::

   IDMap[EXTTYPE_HD][0] = AHCI port 0 drive_s
   bda->hdcount          = 1

固定映射表有空位，因而成功。以后INT 13h看到 ``DL=0x80`` 时，用
``0x80 - EXTSTART_HD = 0`` 取得这一个指针； ``0x80`` 不是第019章写入 ``drive_s`` 的
固有字段，而是本章的映射顺序产生的外部编号。

逻辑CHS不等于磁盘物理布局
------------------------

映射后 ``setup_translation(drive)`` 才最终填写 ``drive->translation`` 与 ``lchs``。
若QEMU通过fw_cfg ``bios-geometry`` 为相同PCI/port路径提供了有效LCHS，SeaBIOS选择
``TRANSLATION_HOST``；没有覆盖时进入heuristic。

QEMU CMOS translation的特殊读取只适用于 ``DTYPE_ATA``，固定盘是 ``DTYPE_AHCI``，
所以不能把legacy ATA的CMOS分支直接套到本章。AHCI heuristic依据IDENTIFY得到的PCHS与
sector count选择none、large或LBA，并把公开cylinder最多裁到1024。磁盘总容量没有固定，
本书也就不制造唯一的head/cylinder数。

这套LCHS服务于旧式INT 13h CHS编码，不改变backend的LBA扇区布局。第022章读第一个扇区
使用CHS 0/0/1；更后的GRUB可以使用EDD/LBA接口。

第一份FDPT进入EBDA并发布IVT 41h
------------------------------

``fill_fdpt(drive, hdid=0)`` 在EBDA ``fdpt[0]`` 写logical cylinders/heads/sectors、
precompensation、drive-control byte和landing zone。若LCHS与PCHS不同，它还填physical
字段、 ``0xa0`` translation signature和checksum；相同则不制造extended translation
字段。

不论是否翻译，第一块硬盘的IVT 41h都被改成指向EBDA ``fdpt[0]``。只有第二块硬盘才使用
IVT 46h，第三块及以后不再写FDPT。固定单盘路径到此形成：

::

   DL 0x80
   → IDMap[EXTTYPE_HD][0]
   → persistent AHCI port 0 drive_s

但还没有发出任何AHCI READ command。

generic hard-disk动作成为BEV[0]
------------------------------

``map_hd_drive`` 返回后，第一次 ``add_bev(IPL_TYPE_HARDDISK, 0)`` 看到
``HaveHDBoot=0``，将其后增为1并写：

::

   BEV[0].type   = IPL_TYPE_HARDDISK
   BEV[0].vector = 0

vector为0是因为generic hard-disk动作由SeaBIOS按type分派到 ``boot_disk(0x80, 1)``，
并非far call vector。多块SeaBIOS硬盘仍会各自按BootList顺序进入 ``IDMap[0x80...]``，
但后续hard-disk ``add_bev`` 会被 ``HaveHDBoot`` 去重，只留下一个从当前0x80开始的启动
动作。

固定iPXE只是复制进BEV[1]
-----------------------

第二个BootList条目是 ``IPL_TYPE_BEV``。它走switch的default分支：

.. code-block:: c

   add_bev(pos->type, pos->data);

于是：

::

   BEV[1].type   = IPL_TYPE_BEV
   BEV[1].vector = iPXE ROM segment:0385

iPXE仍未执行。第022章以后只有generic hard-disk启动失败并进入INT 18h/下一项，或用户
此前把iPXE移到链表头时， ``do_boot`` 才会选择该vector。

固定路径没有call_bcv
--------------------

如果BootList含 ``IPL_TYPE_BCV``，遍历会：

.. code-block:: c

   call_bcv(pos->vector.seg, pos->vector.offset);
   add_bev(IPL_TYPE_HARDDISK, 0);

``call_bcv`` 通过与Option ROM init相同的16位big-real调用边界执行连接代码，传入的BDF
参数为0。BCV可以安装/链式接管INT 13h或建立ROM自己的drive服务；SeaBIOS没有与该条目
关联的 ``drive_s`` 可写入IDMap，所以只增加generic hard-disk启动动作。

第020章已经核定固定e1000e ``BCV=0``，也没有legacy/storage ROM；固定BootList因而不含
``IPL_TYPE_BCV``，本次遍历没有调用 ``call_bcv``。标题中的“处理BCV”是解释该类型的真实
分支，不把条件能力伪装成本次事件。

末尾fallback形成固定BEV[2]
-------------------------

遍历结束后，源码无条件尝试：

.. code-block:: c

   add_bev(IPL_TYPE_FLOPPY, 0);
   add_bev(IPL_TYPE_HARDDISK, 0);

固定此前没有floppy BootList条目， ``HaveFDBoot=0``，所以generic floppy被写成
``BEV[2]``；它没有对应 ``IDMap[EXTTYPE_FLOPPY][0]``，真正尝试时会由INT 13h失败。末尾
hard-disk调用因 ``HaveHDBoot`` 已非0而被去重。

因此固定最终序列精确为：

::

   BEV[0] = generic hard disk → boot_disk(0x80, checksig=1)
   BEV[1] = iPXE BEV          → far call ROM vector
   BEV[2] = generic floppy    → boot_disk(0x00, conditional fallback)

它不是“只有一个硬盘项”，也不包含当前未发现的CD。

cdrom_prepboot在CDCount为0时返回
------------------------------

固定没有ATAPI/USB CD， ``CDCount=0``。 ``cdrom_prepboot()`` 在检查到0后返回，不分配
``DTYPE_CDEMU`` drive，也不改变BDA ``hdcount``。条件CD路径才会为之后的El Torito
emulation预留F-segment drive。

pmm_prepboot撤销可发现的PMM入口
------------------------------

``pmm_init()`` 在早期POST已给 ``PMMHEADER`` 写signature、entry和checksum，供Option ROM
init/BCV阶段请求内存。现在所有固定ROM init完成且没有BCV，MainThread调用
``pmm_prepboot()``：

.. code-block:: c

   PMMHEADER.signature = 0;
   PMMHEADER.entry.segoff = 0;

这撤销了可发现的POST Memory Manager入口。顺序不能提前到条件BCV之前，也不应延后到
boot sector已经运行以后。

malloc_prepboot收尾内存，但不产生“冻结开关”
-----------------------------------------

仍在MainThread上， ``malloc_prepboot()`` 精确执行：

* 从最后确认的 ``RomEnd`` 到 ``rom_get_max()`` 清零未用ROM区；
* 开启upper-memory配置时在上界放置dummy Option ROM header；
* 把 ``BDA.mem_size_kb`` 以上到低RAM末端的范围加入E820 ``RESERVED``；
* 清零 ``ZoneFSeg`` 最低未用区；
* 将 ``ZoneHigh`` 最低空闲范围中按页对齐的部分通过 ``e820_add(..., E820_RAM)`` 归还；
* 重新计算 ``LegacyRamSize``。

这些步骤形成交给bootloader的最终内存占用结果，但源码没有设置一个“allocator/E820永久
锁定”bit。随后 ``e820_prepboot()`` 的实现只调用 ``dump_map()``；它输出当前最终map，
不再增删entry。当前控制流后面也没有新的E820修改，所以可以说本次handoff map已经确定，
不能把 ``dump_map`` 本身解释成锁。

HaveRunPost与BIOS checksum是prepareboot最后两次写
----------------------------------------------

SeaBIOS在 ``code_mutable_preinit()`` 已把 ``HaveRunPost`` 从0设为1，表示POST进行中。
MainThread现在写：

.. code-block:: c

   HaveRunPost = 2;

``in_post()`` 因而不再返回true；QEMU shadow/reboot逻辑也能区分完成状态。值3属于恢复原始
shadow失败后的reboot-loop防护，不是本章正常出口。

最后：

.. code-block:: c

   BiosChecksum -= checksum((u8*)0xf0000, 64 * 1024);

``BiosChecksum`` 自身位于该64 KiB BIOS segment内。减去当前8-bit和后，新segment总和
成为0 modulo 256。这个字节仍可写，因为 ``make_bios_readonly()`` 尚未调用。

``prepareboot()`` 随即返回 ``maininit()``。本章严格停在下一条
``make_bios_readonly()`` 之前，不提前清0x7000..EBDA、不触发INT 19h，也不读取MBR。

本章结束状态
------------

* current executor：BSP上的SeaBIOS ``MainThread``， ``prepareboot()`` 刚返回；
* CPU/mode：32位保护模式，分页关闭，A20开启，MainThread IF=0；
* threads： ``have_threads=false``；菜单后的第二次 ``wait_threads`` 固定没有迭代；
* menu：默认提示已等待2500 ms，固定无输入，BootList顺序未改；
* BCV：固定BootList没有BCV， ``call_bcv`` 调用次数为0；条件分支已在正文固定；
* hard-disk map： ``IDMap[EXTTYPE_HD][0]`` 指向AHCI port 0，BDA ``hdcount=1``，
  ``DL=0x80`` 将解析到该drive；
* geometry：translation/LCHS已按host override或AHCI heuristic确定；精确数值随固定磁盘
  容量/几何输入而变，不在正文伪造；
* FDPT：EBDA ``fdpt[0]`` 已填写，IVT 41h已发布；IVT 46h未用于第二盘；
* final boot actions： ``BEV[0]=hard disk``、 ``BEV[1]=iPXE``、
  ``BEV[2]=floppy fallback``；BootList本身仍存在；
* CD emulation： ``CDCount=0``，未建立 ``DTYPE_CDEMU``；
* TPM/PMM：TPM仍不存在；PMM header signature与entry已清零；
* memory handoff： ``malloc_prepboot`` 已完成，当前最终E820 map已dump；没有E820锁位；
* POST/checksum： ``HaveRunPost=2``，0xf0000..0xfffff的8-bit checksum已调为0；
* BIOS shadow：尚未重新写保护；
* MBR、0x7c00、GRUB、Linux：均未读取或执行；
* next entry： ``make_bios_readonly()``。

关键边界
--------

#. 固定无输入菜单只等待并返回；用户选择只移动BootList条目，不直接启动它。
#. 第二次 ``wait_threads`` 在固定同步路径是空barrier，但为
   ``threads_during_optionroms=true`` 配置保留。
#. fixed e1000e提供BEV而非BCV；本次 ``call_bcv=0``。
#. ``bcv_prepboot`` 遍历BootList并另行填BEV数组，不销毁BootList。
#. ``0x80`` 来自空IDMap/BDA上的第一次 ``map_hd_drive``，不是AHCI探测期属性。
#. AHCI translation不走只针对 ``DTYPE_ATA`` 的QEMU CMOS特殊分支。
#. 多块硬盘可映射多个IDMap slot，但generic hard-disk启动动作只保留一个。
#. fixed final ``BEV[]`` 还含无mapped floppy的fallback，不能简写为只有硬盘与iPXE。
#. ``e820_prepboot`` 只dump当前map；本章结果稳定来自后续路径不再修改，不来自锁。
#. checksum更新发生在shadow重新写保护之前。

下一入口
--------

``maininit()`` 下一条语句是：

.. code-block:: c

   make_bios_readonly();

第022章将从q35 PAM shadow写保护开始，再由 ``startBoot()`` 清POST临时低内存并调用
INT 19h。固定 ``BEV[0]`` 选择generic hard disk，INT 13h才会沿
``DL=0x80 → IDMap[EXTTYPE_HD][0] → AHCI port 0`` 读取LBA 0到0x7c00。

资料
----

* `SeaBIOS：maininit菜单、barrier与prepareboot顺序 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c#L195-L234>`_；
* `SeaBIOS：prepareboot精确收尾顺序 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c#L160-L179>`_；
* `SeaBIOS：启动菜单的默认等待与选择动作 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/boot.c#L625-L794>`_；
* `SeaBIOS：BEV数组、BCV处理、drive map与fallback <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/boot.c#L796-L858>`_；
* `SeaBIOS：BDA/EBDA在POST开始清零 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c#L73-L99>`_；
* `SeaBIOS：IDMap、translation、FDPT与map_hd_drive <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/block.c#L31-L299>`_；
* `SeaBIOS：INT 13h按DL解析IDMap <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/disk.c#L699-L726>`_；
* `SeaBIOS：无CD时cdrom_prepboot返回 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/cdrom.c#L105-L125>`_；
* `SeaBIOS：PMM入口初始化与撤销 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/pmm.c#L154-L176>`_；
* `SeaBIOS：malloc_prepboot的实际内存修改 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/malloc.c#L530-L566>`_；
* `SeaBIOS：e820_prepboot只dump map <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/e820map.c#L140-L152>`_；
* `SeaBIOS：HaveRunPost的进行中/完成状态 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c#L288-L300>`_；
* `SeaBIOS：无TPM时prepboot helper的出口 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/tcgbios.c#L1240-L1283>`_；
* `QEMU：PC默认boot order cad及CMOS编码 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/pc.c#L251-L290>`_；
* `BIOS Enhanced Disk Drive Specification <https://www.t13.org>`_。
