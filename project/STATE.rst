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
   audit verified       = 001-033
   verified_through     = 033
   blocked batches      = none
   next batch           = 034-036
   next batch status    = ready

历史正文已经写到第193章，但只有001—033按
``project/LINUX_KERNEL_CONTRACT.rst`` 完成固定源码审查。034—193仍是 ``pending``，
不得把“文件存在”写成“技术内容已验证”。第193章之后的新生产保持暂停。

最近完成批次
------------

`031—033审查报告 <audits/linux-kernel/031-033.rst>`_：状态 ``repaired``。

本批修复了：

* 把三章旧版本与版本化路径改为固定Linux 7.2-rc1、``/boot/bzImage`` 和
  ``/boot/initramfs.img``；
* 把Linux setup header字段分为固定源码常量、build/config/link产物值和runtime allocator值，
  不再从commit虚构最终artifact数字；
* 核定 ``grub_cmd_linux`` 的module ref、header校验、2048-byte command-line capacity、
  protected payload/init-size差异、relocator current/target、parameter改写、file close和loader
  publication；
* 核定 ``grub_cmd_initrd`` 的single raw component、true/aligned size、上下界、4 KiB target、
  ramdisk字段与component/chunk所有权；
* 记录两个command真实的不完整失败回滚，撤销“任意错误都完整释放”的旧概括；
* 核定implicit boot、flags0 machine fini、当前empty preboot chain、low boot-params chunk、
  physical command-line pointer、E820与relocator身份分离；
* 核定relocator32的flat GDT、paging/PAE关闭、IF/DF清除和far jump；
* 撤销“所有handoff寄存器都为0”的错误：``EAX/ECX/EDX`` 未由固定GRUB源码赋值，按协议标为
  unspecified；
* 三章均按连续时间线重写，章末统一为
  ``本章结束状态 → 关键边界 → 下一入口 → 资料``。

第033章已验证结束状态
---------------------

符号来自实际artifact/runtime，不制造缺失数字：

::

   S = effective setup_sects
   F = /boot/bzImage file size
   P = F - 512 - S*512
   I = setup_header.init_size
   K = protected payload physical target
   N = /boot/initramfs.img true size
   A = ALIGN_UP(N,4096)
   R = initramfs physical target
   C = command-line offset in low chunk
   Q = low chunk total size
   Z = boot_params physical target

精确交接状态：

::

   current executor       = Linux 7.2-rc1 compressed startup_32
   exact next instruction = cld
   CPU                    = BSP / CPU0
   CPU mode               = 32-bit protected mode
   paging                 = off; CR0.PG=0
   PAE                    = off; CR4.PAE=0
   A20                    = on
   IF / DF                = 0 / 0
   GDT                    = relocator32 flat GDT
   CS                     = 0x10 flat execute/read
   DS/ES/FS/GS/SS         = 0x18 flat read/write
   EIP                    = K
   ESI / ESP              = Z / Z
   EBP / EDI / EBX        = 0 / 0 / 0
   EAX / ECX / EDX        = unspecified
   boot_params            = final copy at Z
   command line pointer   = Z+C
   command line           = BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0
   protected payload      = at K; not decompressed
   initramfs              = N raw bytes at R; not unpacked
   16-bit Linux setup     = not executed
   GRUB return path       = none after successful far jump
   open file/device/fs    = none

关键已验证关系
--------------

* fixed Linux header：

  ::

     boot_flag       = 0xaa55
     HdrS            = present
     protocol        = 0x020f
     LOADED_HIGH     = set
     original code32_start = 0x00100000
     initrd_addr_max = 0x7fffffff
     cmdline_size    = 2047

* ``P`` 是file payload length，``I`` 是初始化窗口；GRUB只读 ``P`` 字节但为
  ``PAGE_ALIGN(I)`` 取得protected chunk；
* adjusted ``code32_start = K + 0x100000 - 0x100000 = K``；
* ``linux_params.boot_flag`` 在artifact通过0xaa55校验后被GRUB清零；
* fixed kernel command line：

  ::

     BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0

* initrd有效上界：

  ::

     min(0x7fffffff, 0x37ffffff) - 0x10000 = 0x37feffff

* initrd target lower bound：

  ::

     R >= K + PAGE_ALIGN(I)

* ``ramdisk_image=R``、``ramdisk_size=N``；``A-N`` 页尾不是有效内容且不保证清零；
* high address preference不保证 ``R`` 等于最高候选；
* current simple-install path没有注册preboot hook，``grub_loader_boot`` 的preboot loop执行0次；
* relocator chunk不是 ``grub_mmap`` overlay，final E820可继续把K/R/Z所在firmware RAM报告为RAM；
* Linux通过 ``EIP/ESI``、``init_size``、``cmd_line_ptr`` 和ramdisk字段识别这些对象；
* fixed GRUB只给 ``EBP/EDI/EBX/ESI/ESP/EIP`` 相关字段赋值，``EAX/ECX/EDX`` 不具备handoff
  contract。

固定磁盘内容约定
----------------

::

   /boot/grub/grub.cfg:
     set timeout=0
     set default=0
     menuentry 'Linux 7.2-rc1' {
         linux /boot/bzImage root=/dev/sda1 ro console=ttyS0
         initrd /boot/initramfs.img
     }

``/boot/bzImage`` 固定为Linux release 7.2-rc1、gregkh/linux commit
``7404ce51637231382873d0b55edabc2f3b841a9d`` 构建结果；initramfs与本场景匹配。
这些是显式镜像约定，不是源码commit自动产生的artifact路径。具体file size、build config、
inode、extent、data LBA与runtime target仍不得制造数值。

下一入口
--------

第034章从fixed Linux compressed entry继续：

.. code-block:: asm

   arch/x86/boot/compressed/head_64.S:

   startup_32:
       cld
       cli
       leal (BP_scratch+4)(%esi), %esp
       call 1f
   1:
       popl %ebp
       subl $rva(1b), %ebp

034—036必须重新核定：

* scratch stack取得runtime ``startup_32`` base的精确寄存器变化；
* Linux自有GDT、data selectors、16 KiB boot stack和32-bit far return；
* ``verify_cpu`` 的fixed 7.2-rc1检查、failure halt边界和本场景成功条件；
* build-derived ``kernel_alignment``、``init_size`` 如何进入temporary relocation base；
* ``CONFIG_AMD_MEM_ENCRYPT``、SEV、5-level paging与KASLR的build/runtime条件，不能默认执行；
* 6-page early 4-level page table、4 GiB identity map、CR4.PAE/CR3/EFER.LME/CR0.PG和
  compatibility-to-64-bit transition；
* compressed ``startup_64`` 保存boot params、选择安全搬移区、处理BSS/identity map和进入
  decompressor前的自然分章；
* 第037章入口必须与第036章出口对齐，但第037章正文留给后续顺序批次。

034—036批次必须先读取
--------------------

#. ``AGENTS.md``；
#. ``project/LINUX_KERNEL_CONTRACT.rst``；
#. 本文件；
#. ``project/audits/linux-kernel/index.rst``；
#. ``project/audits/linux-kernel/031-033.rst`` 的“已核定的整批成功路径”、
   “对象、引用与状态边界”、“失败与未发生边界”和“连续性检查”；
#. 第033章末尾、第034—036章全文和第037章开头；
#. 两份track manifest的审计游标片段；
#. fixed Linux ``Documentation/arch/x86/boot.rst``、
   ``arch/x86/boot/compressed/head_64.S``、``arch/x86/kernel/verify_cpu.S``、
   ``arch/x86/include/asm/boot.h``、page/segment/MSR/control-register constants及本批实际进入的
   compressed helper；
#. 若正文进入KASLR/identity-map/decompressor C路径，再读取对应fixed source；不要只凭旧章标题
   推断；
#. 本批已完成GRUB handoff，除非发现033出口矛盾，不重新展开001—032。

固定源码工作树
--------------

::

   /Volumes/LinuxKernel/seabios HEAD       = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   /Volumes/LinuxKernel/qemu HEAD          = a759542a2c62f0fd3b65f5a66ad9868201014669
   /Volumes/LinuxKernel/grub HEAD          = d38d6a1a9b79427848976f53d474392cd29c2a71
   /Volumes/LinuxKernel/linux-7.2-rc1 HEAD = 7404ce51637231382873d0b55edabc2f3b841a9d

四个固定工作树均为完整checkout而非sparse checkout，且必须保持干净。
``/Volumes/LinuxKernel/linux`` 是原有master工作树，不作为正文证据；固定Linux worktree由该仓库创建，
避免改变master。项目内 ``.sources/`` 不再承担当前源码缓存；旧 ``.gitignore`` 规则保留，防止未来误加
临时源码目录。

已知结构与内容债务
------------------

* 第034章起的历史启动正文仍有旧版本标签、未经fixed source复核的build/runtime数值和旧章末结构；
* 第065章存在两个正文文件；
* 第066章存在两个正文文件；
* 001—073尚未逐章登记到当前track manifest；
* 034—193尚未按专用合同补齐章末结构和精确证据，必须随顺序审查处理，不能批量机械改写。

历史前向终点
------------

回溯审查开始前的第193章终点保存在
``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst``。它只用于审查闭合后的对照，不是当前
执行依据，也不代表UDP入口已经验证。
