Linux Kernel
============

本路径从机器真正开始执行的地方进入 Linux：设备上电。

当前正文
--------

#. `设备上电后，x86-64 Linux 内核怎样被装入并完成解压？ <01-power-on-to-decompression.rst>`_

当前主线
--------

第一篇固定使用：

::

   x86-64
   → SeaBIOS
   → GRUB
   → bzImage
   → Linux 6.12.95

正文从 CPU 复位后执行固件开始，依次追踪固件、bootloader、Linux boot protocol、16 位 setup、
保护模式入口、64 位压缩启动桩和 ``extract_kernel()``，直到跳入解压后的
``arch/x86/kernel/head_64.S:startup_64``。

写法
----

内容按实际发生顺序连续叙述。每个阶段直接说明当前执行者、CPU 模式、内存中的代码与数据、完成的状态
以及下一次控制权跳转。概念在流程需要时解释，不先安排世界观、阅读方法、源码导航或构建系统章节。

旧 Roadmap
----------

``aiBook`` 的 Linux Kernel Roadmap 在启动部分之前安排了四个 Part、20 章内容，真正的固件、bootloader
和内核解压位于 Part 5。它仍用于确认需要覆盖的知识，开篇顺序不再沿用。