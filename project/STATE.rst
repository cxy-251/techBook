项目状态
========

最后更新
--------

2026-07-15。

当前模式
--------

::

   mode                 = retrospective-audit
   forward production   = paused
   content present      = 001-193
   audit verified       = 001-003
   verified_through     = 003
   blocked batches      = none
   next batch           = 004-006
   next batch status    = ready

历史正文已经写到第193章，但只有001—003按
``project/LINUX_KERNEL_CONTRACT.rst`` 完成固定源码审查。004—193仍是 ``pending``，
不得把“文件存在”写成“技术内容已验证”。第193章之后的新生产保持暂停。

最近完成批次
------------

`001—003审查报告 <audits/linux-kernel/001-003.rst>`_：状态 ``repaired``。

本批修复了：

* 第001章旧的 ``Linux 6.12.95`` 标签，并补入QEMU reset与BIOS映射证据；
* 第002章把固定QEMU中已经有效的A20误写成SeaBIOS首次打开的问题；
* 第002章对冷启动 ``cli``/``cld`` 幂等边界的缺失；
* 第003章没有固定 ``CONFIG_RELOCATE_INIT=y`` 却无条件叙述重定位的问题；
* 第003章把初始栈顶 ``0x7000`` 写成进入 ``maininit()`` 后精确ESP的问题；
* 三章缺失的合同章末结构与关键固定源码行锚。

第003章已验证结束状态
---------------------

::

   current executor       = relocated SeaBIOS maininit()
   current CPU            = BSP
   CPU mode               = 32-bit protected mode
   paging                 = disabled
   A20                    = enabled
   maskable interrupts    = disabled
   early stack            = top initialized at 0x7000
   current ESP            = below 0x7000; exact value not fixed
   low BIOS mapping       = writable shadow RAM
   HaveRunPost            = 1 (POST started, not completed)
   initial E820           = present
   ZoneTmpLow/ZoneTmpHigh = initialized
   ZoneHigh               = initialized and E820-reserved
   code32init             = relocated to temporary RAM
   GRUB/Linux             = not loaded

下一入口
--------

第004章从重定位后的 ``maininit()`` 第一条调用开始：

::

   maininit()
   → interface_init()
   → malloc_init()
   → qemu_cfg_init()/coreboot_cbfs_init()/multiboot_init()
   → ivt_init()
   → bda_init()

004—006批次必须先读取：

#. ``AGENTS.md``；
#. ``project/LINUX_KERNEL_CONTRACT.rst``；
#. 本文件；
#. ``project/audits/linux-kernel/index.rst``；
#. ``project/audits/linux-kernel/001-003.rst`` 的“第003章”与“连续性检查”；
#. 第003章末尾、第004—006章正文和第007章开头；
#. ``.sources/seabios`` 固定提交中当前符号涉及的源码。

不要读取001—002全文、完整193章目录或历史前向检查点，除非审查中发现必须回溯的矛盾。

源码缓存
--------

::

   .sources/seabios HEAD = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   .sources/qemu HEAD    = a759542a2c62f0fd3b65f5a66ad9868201014669

两个缓存均由 ``.gitignore`` 排除。QEMU使用稀疏检出；缺少目录时按当前批次补齐。

已知结构债务
------------

* 第065章存在两个正文文件；
* 第066章存在两个正文文件；
* 001—073尚未逐章登记到当前track manifest；
* 第004章历史正文仍把早期栈描述成“仍位于0x7000”，需要在下一批按当前ESP/栈顶边界核验；
* 004—193尚未按专用合同补齐章末结构和精确证据，必须随顺序审查处理，不能批量机械改写。

历史前向终点
------------

回溯审查开始前的第193章终点保存在
``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst``。它只用于审查闭合后的对照，不是当前
执行依据，也不代表UDP入口已经验证。
