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
   audit verified       = 001-036
   verified_through     = 036
   blocked batches      = none
   next batch           = 037-039
   next batch status    = ready

历史正文已经写到第193章，但只有001—036按
``project/LINUX_KERNEL_CONTRACT.rst`` 完成固定源码审查。037—193仍是 ``pending``，不得把
“文件存在”写成“技术内容已验证”。第193章之后的新生产保持暂停。

最近完成批次
------------

`034—036审查报告 <audits/linux-kernel/034-036.rst>`_：状态 ``repaired``。

本批完成：

* 三章从旧Linux 6.12.95历史稿整章重写为固定Linux 7.2-rc1 commit；
* 将 ``K`` 当前compressed副本、``O0`` 初步解压基址与 ``B`` compressed安全搬迁基址分开；
* 核定scratch stack、Linux GDT、16 KiB stack、 ``verify_cpu``、failure halt与完整
  ``CR0_STATE``；
* 证明startup_32的六页early table直接建立在 ``B+rva(pgtable)``，但far return仍进入当前
  ``K+0x200``；
* 核定stage1 IDT仅提供条件 ``#VC``，stage2才加入 ``#PF``、NMI和条件 ``#VC``；
* 删除旧稿不存在的 ``CONFIG_X86_5LEVEL`` gate，按fixed command line与runtime CPUID.LA57
  保留4-level/4-to-5两种结果；
* 核定low 8 KiB trampoline save/use/restore、 ``[startup_32,_bss)`` backward copy、BSS clear与
  ``.pgtable`` 三个不同边界；
* 核定explicit identity maps只含relocated image、boot params、2048-byte command line和
  setup_data；高地址output由stage2 ``#PF`` 按2 MiB demand-map；
* 证明 ``console=ttyS0`` 不触发compressed early-serial parser；
* 核定KASLR avoid ranges、E820 slot、physical fallback与virtual selection的独立语义；
* 把unaccepted-memory条件收紧为当前legacy BIOS ``EFI_TYPE_NONE`` 下精确不执行；
* 三章章末统一为 ``本章结束状态 → 关键边界 → 下一入口 → 资料``。

当前符号账本
------------

::

   K  = GRUB交付的protected payload/startup_32物理起点
   Z  = final boot_params物理地址
   I  = hdr.init_size
   N  = /boot/initramfs.img true size
   R  = initramfs物理起点
   G  = boot_params中GRUB实际交付的hdr.kernel_alignment
   L  = build产生的LOAD_PHYSICAL_ADDR
   E  = rva(_end)，compressed运行映像跨度
   O0 = CONFIG_RELOCATABLE ? max(ALIGN_UP(K,G),L) : L
   B  = O0 + I - E
   D  = ALIGN_UP(max(output_len,kernel_total_size),2 MiB)
   O  = KASLR选择后的物理解压输出
   V  = KASLR选择后的正式内核虚拟位置量

``G/L/I/E/output_len/kernel_total_size`` 依最终build/link artifact；``K/Z/R`` 依GRUB runtime；
``O/V`` 还依KASLR config、entropy、CPU与E820。固定源码核定关系，不补造缺失数字。

第036章已验证结束状态
---------------------

::

   current executor       = Linux 7.2-rc1 compressed extract_kernel()
   exact next action      = call decompress_kernel(O,V,error), not executed
   CPU                    = BSP / CPU0
   CPU mode               = 64-bit long mode
   IF / DF                = 0 / 0
   current code base      = B relocated compressed copy
   current stack          = B+rva(boot_stack), 16 KiB
   R15 / RBP / RBX        = Z / O0 / B
   compressed BSS         = zeroed
   paging level           = runtime 4-level or 5-level from CPUID.LA57
   stage2 IDT             = #PF + NMI + conditional #VC
   explicit maps          = relocated image + boot_params + 2048-byte cmdline + setup_data
   demand maps            = non-present supervisor #PF adds one 2 MiB identity range
   boot_params_ptr        = Z; sanitized after relocation
   command line           = BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0
   early serial           = not enabled by console=ttyS0 in compressed parser
   boot heap              = initialized; size depends on compression build
   needed_size            = D
   output / virt_addr     = O / V, selected and hard-validated
   unaccepted memory      = no accept on current legacy BIOS path
   compressed bitstream   = not decompressed
   ELF/PT_LOAD/relocs     = not processed
   initramfs              = N raw bytes at R; not unpacked and not explicitly identity-mapped

关键已验证关系
--------------

* 地址关系：

  ::

     O0 = max(ALIGN_UP(K,G),L) under CONFIG_RELOCATABLE; otherwise L
     B  = O0 + I - E
     B + E = O0 + I

* startup_32建立：

  ::

     CR3 = B+rva(pgtable)
     1 level-4 + 1 level-3 + 4 level-2 pages
     2048 * 2 MiB = low 4 GiB identity map

* ``CR0_STATE = PE|MP|ET|NE|WP|AM|PG``；LME、PG/LMA、compatibility ``CS`` 与L-bit ``CS`` 是
  四个顺序边界；
* far return目标是 ``K+rva(startup_64)=K+0x200``，不是尚未copy的B副本；
* fixed command line没有 ``no5lvl``，runtime CPUID.LA57为0则保持4-level，为1则通过temporary
  low trampoline执行4-to-5；
* low trampoline使用8 KiB，原内容save/restore，不永久成为E820 reservation；
* backward copy：

  ::

     [K, K+rva(_bss)) -> [B, B+rva(_bss))

* ``[_bss,_ebss)`` 随后清零；``.pgtable`` 位于 ``_ebss`` 之后并保留；
* startup_32来源的4/5-level root都让 ``p4d_offset(root,0)==_pgtable``，所以前六页保留、后26页
  用于扩图；
* explicit identity mapping不包括initramfs或未知KASLR output；stage2 ``#PF`` 对普通
  non-present supervisor access按CR2所在2 MiB补图；
* ``boot_params`` 在configure5level中清洗一次；BSS不跨搬迁复制，``extract_kernel`` 重新发布
  ``boot_params_ptr`` 并再次清洗；
* fixed compressed early serial只解析 ``earlyprintk``、``console=uart8250,io`` 或
  ``console=uart,io``，不解析普通 ``console=ttyS0``；
* ``D=ALIGN_UP(max(output_len,kernel_total_size),2 MiB)``；
* 无 ``CONFIG_RANDOMIZE_BASE`` 时 ``O=O0,V=L``；启用且无 ``nokaslr`` 时物理与虚拟选择独立，
  physical无slot只警告并保留O0，不撤销flag或virtual KASLR；
* 当前i386-pc boot params没有EFI type，``init_unaccepted_memory()`` 返回false。

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
这些是显式镜像约定，不是源码commit自动产生的artifact路径。具体build config、compression、
file size、inode、extent、data LBA、CPU model与runtime addresses仍不得制造数值。

下一入口
--------

第037章从fixed compressed C调用继续：

.. code-block:: c

   entry_offset = decompress_kernel(output, virt_addr, error);

037—039必须重新核定：

* ``decompress_kernel`` 在当前heap已初始化条件下调用build-selected ``__decompress`` 的精确参数、
  error与 ``ULONG_MAX`` 边界；
* 高地址O首次写入如何通过stage2 ``#PF`` demand-map，而不是假设036已主动映射；
* ``parse_elf`` 复制program headers、只搬 ``PT_LOAD``、relocatable/non-relocatable destination与
  entry offset；
* ``handle_relocations`` 的physical output delta与virtual ``V`` delta，不能把O/V混用；
* ``extract_kernel`` 返回前的exception cleanup、spurious NMI检查、 ``output+entry_offset`` 与
  汇编恢复 ``RSI=Z``；
* compressed ``head_64.S`` 跳入解压后 ``arch/x86/kernel/head_64.S:startup_64`` 后的page-table
  修正、SME/KASLR/LA57条件及跳到 ``common_startup_64`` 的真实边界；
* ``common_startup_64`` 的CR4、identity-map/TLB、CPU number、stack、GDT/IDT、GS base、EFER/CR0
  与 ``initial_code`` 调用；
* ``x86_64_start_kernel`` 的early mapping、BSS、bootdata/command line和架构C清理，及第040章
  ``x86_64_start_reservations`` / generic ``start_kernel`` 入口对齐；
* 037—039旧稿中的6.12.95、config/runtime断言与旧章末结构全部视为pending，不继承为证据。

037—039批次必须先读取
---------------------

#. ``AGENTS.md``、``project/LINUX_KERNEL_CONTRACT.rst`` 与本文件；
#. ``project/audits/linux-kernel/034-036.rst`` 的成功路径、寄存器/页表边界、条件分支、失败与
   连续性检查；
#. 第036章末尾、第037—039章全文和第040章开头；
#. 两份track manifest的审计游标；
#. fixed Linux ``arch/x86/boot/compressed/misc.c``、build-selected decompressor interface、
   ``head_64.S``、``idt_64.c``、``ident_map_64.c``、ELF/relocation constants；
#. fixed Linux ``arch/x86/kernel/head_64.S``、相关 ``head64.c`` / early page-table、CPU entry、
   stack/GDT/IDT/GS/CR4 helper及本批真实进入的源码；
#. 第039章若进入bootdata/microcode/reservation helper，必须读取fixed helper实现，不凭旧标题扩写；
#. 本批不得越过039修正文第040章。

固定源码工作树
--------------

::

   /Volumes/LinuxKernel/seabios HEAD       = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   /Volumes/LinuxKernel/qemu HEAD          = a759542a2c62f0fd3b65f5a66ad9868201014669
   /Volumes/LinuxKernel/grub HEAD          = d38d6a1a9b79427848976f53d474392cd29c2a71
   /Volumes/LinuxKernel/linux-7.2-rc1 HEAD = 7404ce51637231382873d0b55edabc2f3b841a9d

四个固定工作树均为完整checkout、非shallow、无active sparse-checkout且干净。
``/Volumes/LinuxKernel/linux`` 是用户原有master工作树，不作为正文证据。项目内 ``.sources/``
不承担当前源码缓存； ``.gitignore`` 规则保留，防止误提交临时源码。

已知结构与内容债务
------------------

* 第037章起的历史启动正文仍有旧版本标签、未经fixed source复核的build/runtime数值和旧章末结构；
* 第065章存在两个正文文件；
* 第066章存在两个正文文件；
* 001—073尚未逐章登记到当前track manifest；
* 037—193尚未按专用合同补齐章末结构和精确证据，必须随顺序审查处理，不能批量机械改写。

历史前向终点
------------

回溯审查开始前的第193章终点保存在
``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst``。它只用于审查闭合后的对照，不是当前执行依据，
也不代表UDP入口已经验证。
