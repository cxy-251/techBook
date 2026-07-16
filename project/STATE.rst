项目状态
========

最后更新
--------

2026-07-16。

当前模式
--------

::

   mode                 = retrospective-audit
   forward production   = paused
   content present      = 001-193
   audit verified       = 001-024
   verified_through     = 024
   blocked batches      = none
   next batch           = 025-027
   next batch status    = ready

历史正文已经写到第193章，但只有001—024按
``project/LINUX_KERNEL_CONTRACT.rst`` 完成固定源码审查。025—193仍是 ``pending``，
不得把“文件存在”写成“技术内容已验证”。第193章之后的新生产保持暂停。

最近完成批次
------------

`022—024审查报告 <audits/linux-kernel/022-024.rst>`_：状态 ``repaired``。

本批修复了：

* 第022章撤销不存在的E820 ``frozen``，把 ``startBoot`` 清零上界收紧为固定
  ``BUILD_EBDA_MINIMUM=0x90000``；
* 第022章核定q35 PAM的 ``0x10/0x11/0x31/0x33`` 语义，区分只读ROM/padding与仍需可写的
  运行期ZoneLow；
* 第022章把LBA 0命令固定为AHCI ``READ DMA(0xc8)``，并补齐固定无TPM、A20、NMI、IF/DF、
  外部栈和INT 18h失败边界；
* 第023章把“LBA 1连续embedding”从无证据固定事实改为显式clean-gap布局约定，保留
  ``kernel_sector``/blocklist为运行时权威；
* 第023章纠正安装器会复制旧 ``0x55aa`` 的错误：旧MBR复制止于0x1fd，新签名来自
  ``boot.img`` 模板；
* 第023章固定 ``boot_drive=ff``、drive check、SeaBIOS EDD返回、AHCI READ DMA，并把
  ``diskboot.img`` 入口栈从错误的 ``SP=2000`` 修为压入DX后的 ``SP=1ffe``；
* 第024章证明第一callback只登记first sector，余下连续LBA 2..N才合并成
  ``start=2,len=N-1,segment=0820`` 的单entry；具体N仍不编造；
* 第024章补齐每批0x7f/SeaBIOS 64 KiB边界、entry先变更后I/O、低LBA READ DMA、错误只自旋
  不INT 18h，以及终点SP/EBP/DI/ES和被原地消耗的blocklist游标。

第024章已验证结束状态
---------------------

::

   current executor       = GRUB 2.14 startup_raw at its first instruction
   current CPU            = BSP
   CPU mode               = 16-bit real mode
   paging                 = disabled
   A20                    = enabled; startup_raw will verify it independently
   FLAGS                  = IF=1, DF=0
   CS:IP                  = 0000:8200
   DL                     = 0x80
   DS / SS                = 0 / 0
   SP                     = 0x1ffe
   stack top              = boot.img-saved startup DX
   ES                     = last diskboot copy destination segment; not inherited as an input
   EBP                    = low32(first remaining entry LBA) = 2 under clean-gap convention
   DI                     = zero-length blocklist terminator
   clean-gap convention   = embedded sectors LBA 1..N contiguous; N unknown without artifact
   diskboot.img           = 0x8000..0x81ff
   startup_raw            = begins at 0x8200
   core.img low copy      = all N embedded sectors loaded contiguously from 0x8000
   blocklist entry        = consumed in place: len=0; start/segment advanced to end
   BIOS bounce buffer     = 0x70000; contains final successful read batch residue
   SeaBIOS disk service   = still callable through INT 13h / DL=0x80
   q35 AHCI               = active; last batches used non-queued READ DMA(0xc8)
   protected mode         = not yet enabled by GRUB
   decompressed GRUB core = not yet produced
   grub_main              = not yet called
   Linux                  = not loaded / not executing

下一入口
--------

第025章从 ``grub-core/boot/i386/pc/startup_raw.S:_start`` 的第一条远跳继续：

::

   0000:8200
   → ljmp 0:ABS(codestart)
   → CLI
   → DS=SS=ES=0; ESP=GRUB_MEMORY_MACHINE_REAL_STACK
   → STI
   → save DL to boot_drive
   → INT 13h AH=00 reset
   → real_to_prot

025—027批次必须先读取：

#. ``AGENTS.md``；
#. ``project/LINUX_KERNEL_CONTRACT.rst``；
#. 本文件；
#. ``project/audits/linux-kernel/index.rst``；
#. ``project/audits/linux-kernel/022-024.rst`` 的“已核定的整批成功路径”、
   “失败与未发生边界”、“发现并修复”和“连续性检查”；
#. 第024章末尾、第025—027章全文和第028章开头；
#. 两份track manifest的审计游标片段；
#. 固定GRUB源码中 ``startup_raw.S``、real/protected-mode转换、A20、RS decoder、decompressor、
   kernel relocation、 ``grub_main`` 和相邻handoff；
#. 第025章INT 13h reset需要的固定SeaBIOS入口；只有正文确实下钻设备副作用时才补读固定QEMU
   AHCI reset实现。

不要读取001—023全文、完整193章目录或历史前向检查点，除非审查中发现必须回溯的矛盾。

源码缓存
--------

::

   .sources/seabios HEAD = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   .sources/qemu HEAD    = a759542a2c62f0fd3b65f5a66ad9868201014669
   .sources/grub HEAD    = d38d6a1a9b79427848976f53d474392cd29c2a71

三个缓存均由 ``.gitignore`` 排除且源码worktree干净。QEMU和GRUB使用稀疏检出；GRUB缓存由
022—024批次按需创建，当前包含boot/diskboot/startup_raw、offset、setup和mkimage等本批文件。
下一批缺少文件时继续按需补齐，不为未来章节预读全部源码。

已知结构债务
------------

* 第025章既有正文把 ``startup_raw`` 的保存DL与INT 13h reset先后写反；固定源码是先
  ``movb %dl,boot_drive``，后 ``int $0x13``，025—027批次必须修正；
* 第065章存在两个正文文件；
* 第066章存在两个正文文件；
* 001—073尚未逐章登记到当前track manifest；
* 025—193尚未按专用合同补齐章末结构和精确证据，必须随顺序审查处理，不能批量机械改写。

历史前向终点
------------

回溯审查开始前的第193章终点保存在
``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst``。它只用于审查闭合后的对照，不是当前
执行依据，也不代表UDP入口已经验证。
