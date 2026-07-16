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
   audit verified       = 001-039
   verified_through     = 039
   blocked batches      = none
   next batch           = 040-042
   next batch status    = ready

037—193中文件存在不等于技术已验证；当前实际pending范围已推进为040—193。第193章审查闭合前
不生产新章节。

最近完成批次
------------

`037—039审查报告 <audits/linux-kernel/037-039.rst>`_：状态 ``repaired``。

本批修复了：

* fixed relocation tail实际只有32-bit与64-bit两组，删除旧稿inverse 32-bit第三组；
* 物理O用于定位relocation target，虚拟V决定x86-64写入delta；
* 高地址O首次写入沿compressed stage2 ``#PF`` demand-map；
* formal startup先 ``GSBASE=0``，common取得CPU0后才写per-CPU offset；
* formal ``verify_cpu`` 返回值未被测试； ``phys_base/load_delta=O`` 而不是O-L；
* startup/common bringup IDT只负责条件 ``#VC``，general early exception table到039才安装；
* 第037章transition identity PMD无global，038的CR4 PGE序列不再被夸写成必然清旧compressed项；
* formal BSS/brk到039统一清零，boot params与完整含 ``BOOT_IMAGE`` 的command line用
  ``__va(Z)`` 复制；
* ``load_ucode_bsp`` 是有条件helper attempt，不等于microcode revision已更新；
* 三章按固定7.2-rc1源码整章重写并统一章末结构。

当前符号
--------

::

   Z = original boot_params physical address
   R/N = original initramfs physical address / true size
   L = build LOAD_PHYSICAL_ADDR
   O = actual physical kernel output base
   V = relocation virtual position value

``O`` 是formal ``phys_base``。``Z`` 只继续作为physical value传给reservations；正式global
``boot_params`` 与 ``boot_command_line`` 已在039复制完成。

第039章结束状态
---------------

::

   current executor       = x86_64_start_reservations(Z), first statement pending
   CPU                    = BSP / logical CPU0
   CPU mode               = 64-bit long mode, kernel high mapping
   IF / DF                = 0 / 0
   current task           = init_task
   current stack          = init_task initial task stack
   GSBASE                 = CPU0 initial per-CPU offset
   GDT                    = CPU0 gdt_page
   CR3                    = early_top_pgt
   temporary identity map = removed from active top-level root
   formal BSS / brk       = zeroed
   general early IDT      = installed
   early direct-map #PF   = available through early_make_pgtable
   global boot_params     = copied and sanitized
   boot_command_line      = copied 2048-byte buffer
   valid command string   = BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0
   init_top_pgt           = conditional KASAN shadow + copied kernel high entry 511
   early microcode        = helper called; actual update conditional/unknown
   initramfs              = R/N recorded in global boot_params; not unpacked
   generic start_kernel   = not called

已验证的037—039关系
-----------------

* decoder输出：

  ::

     __decompress(input_data,input_len,O,output_len)
     parse_elf: dest = O + (p_paddr-L) under CONFIG_RELOCATABLE
     entry_offset = e_entry-L

* relocation：

  ::

     target map adjustment = (O-L)-__START_KERNEL_map
     x86-64 content delta  = V-L

* compressed cleanup把IDTR置空后， ``RSI=Z`` 跳 ``O+entry_offset``；
* formal startup以position-independent helper建立：

  ::

     p2v_offset = runtime physical common_startup_64 - linked virtual common_startup_64
     phys_base   = __START_KERNEL_map + p2v_offset = O

* ``__startup_64`` 修正high tables、只保留actual kernel PMD范围，并建立无global temporary
  identity mapping；
* common startup固定CPU0、 ``current_task=&init_task``、task stack、CPU0 GDT/GSBASE、
  ``EFER.SCE`` 与conditional NXE；
* ``early_setup_idt`` 仍是bringup/VC；039 ``idt_setup_early_handler`` 才安装一般exception和
  direct-map early page-fault helper；
* ``reset_early_page_tables`` 清top-level前511项并reload CR3，之后访问Z必须用direct-map
  ``__va(Z)``；
* 顺序固定为BSS/brk clear → init_top clear → SME flags → KASAN shadow → global TLB flush →
  general early IDT → TDX → copy boot data；
* 命令行复制整个2048-byte buffer，有效字符串保留 ``BOOT_IMAGE=/boot/bzImage``；
* ``init_top_pgt[511]=early_top_pgt[511]`` 只继承kernel high subtree，不是完整direct map。

固定磁盘约定
------------

::

   menuentry 'Linux 7.2-rc1' {
       linux /boot/bzImage root=/dev/sda1 ro console=ttyS0
       initrd /boot/initramfs.img
   }

build ``.config``、compression、file sizes、CPU model、runtime addresses与microcode blob未提供，
不得从commit制造。

下一入口
--------

第040章从fixed ``head64.c``：

.. code-block:: c

   x86_64_start_reservations(char *real_mode_data)
   {
       if (!boot_params.hdr.version)
           copy_bootdata(__va(real_mode_data));
       x86_early_init_platform_quirks();
       ...

当前global ``boot_params.hdr.version`` 已由039 copy得到非零protocol值，普通GRUB路径不再次copy。
040—042需要核定：

* ordinary PC ``hardware_subarch`` 与platform quirks，及generic ``start_kernel`` 第一批调用；
* 第040章出口是否精确停在 ``setup_arch(&command_line)`` 前；
* ``setup_arch`` 接管boot command line、E820与setup_data的fixed 7.2-rc1顺序；
* GRUB E820中K/R/Z仍可能标RAM，与Linux随后reservation/import身份分开；
* ``setup_initial_init_mm``、E820 sanitize/update/finish、kernel resources、max PFN等第042真实边界；
* 第043章 ``early_alloc_pgt_buf`` 入口只作相邻校验，不越序修改。

040—042批次读取清单
-------------------

#. ``AGENTS.md``、合同、本文件与 ``037-039`` 报告；
#. 第039章末尾、040—042全文、043开头；
#. fixed ``head64.c:x86_64_start_reservations``、platform quirks；
#. fixed ``init/main.c:start_kernel`` 到 ``setup_arch``；
#. fixed ``arch/x86/kernel/setup.c`` 及实际调用的cmdline/E820/setup_data/init_mm/resource/PFN helper；
#. 两份manifest游标；不凭旧正文继承函数顺序或具体PFN数字。

固定源码工作树
--------------

::

   /Volumes/LinuxKernel/seabios HEAD       = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   /Volumes/LinuxKernel/qemu HEAD          = a759542a2c62f0fd3b65f5a66ad9868201014669
   /Volumes/LinuxKernel/grub HEAD          = d38d6a1a9b79427848976f53d474392cd29c2a71
   /Volumes/LinuxKernel/linux-7.2-rc1 HEAD = 7404ce51637231382873d0b55edabc2f3b841a9d

均为clean、完整、非shallow、无active sparse checkout。``/Volumes/LinuxKernel/linux`` 不作为
fixed evidence；项目 ``.sources/`` 不承担缓存。

已知债务
--------

* 第040章起历史正文仍有旧版本/未经固定源码复核的断言与旧章末结构；
* 第065、066章各有重复正文文件；
* 001—073尚未逐章进入track machine-readable catalog；
* 040—193必须继续顺序审查，不能批量机械标verified。

历史前向终点
------------

``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst`` 只保存审查开始前的第193章状态，不是当前事实。
