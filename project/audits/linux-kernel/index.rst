Linux Kernel回溯审查账本
========================

本账本只登记批次状态和报告入口。技术证据保存在各批报告与修订后的正文中。

当前游标
--------

::

   mode             = retrospective-audit
   production       = paused
   verified_through = 009
   current_batch    = none
   next_batch       = 010-012
   current_status   = ready

状态语义遵守 ``project/LINUX_KERNEL_CONTRACT.rst``。

批次
----

* `001-003 <001-003.rst>`_：``repaired``；固定QEMU/SeaBIOS源码核验完成，无阻塞。
* `004-006 <004-006.rst>`_：``repaired``；固定SeaBIOS源码核验完成，无阻塞。
* `007-009 <007-009.rst>`_：``repaired``；固定SeaBIOS/QEMU源码核验完成，无阻塞。

已知但尚未轮到的结构债务
------------------------

* 第065章存在两个正文文件；
* 第066章存在两个正文文件；
* 既有boot章节没有逐章登记到当前track manifest；
* 历史正文与通用学习设计规则长期并存，适用关系曾不明确；现由Linux Kernel专用合同消除歧义。

结构债务在顺序审查到对应编号时处理；不会因此把001—064跳过。
