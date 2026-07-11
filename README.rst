techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 入口 <docs/tracks/linux-kernel/index.rst>`_
* `按下电源键后，CPU 从哪里取得第一条指令？ <docs/tracks/linux-kernel/01-power-on-first-instruction.rst>`_

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GRUB i386-pc
   → bzImage
   → Linux 6.12.95

开头从设备上电后的故事进入，最终主题仍然是 Linux 内核。正文按真实发生顺序连续讲述；达到适合一次
阅读的篇幅，并遇到自然控制权交接点时换章。

当前第一章只讲到 SeaBIOS 的 ``reset_vector`` 跳入 ``entry_post``。稳定后再沿同一执行路径继续，
不提前列出后续整本目录。

开始工作
--------

新的对话或助手先阅读：

#. ``AGENTS.md``；
#. `当前状态 <project/STATE.rst>`_；
#. `Linux Kernel 入口 <docs/tracks/linux-kernel/index.rst>`_；
#. 当前正文。