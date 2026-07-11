techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 入口 <docs/tracks/linux-kernel/index.rst>`_
* `设备上电后，x86-64 Linux 内核怎样被装入并完成解压？ <docs/tracks/linux-kernel/01-power-on-to-decompression.rst>`_

当前主线
--------

::

   x86-64
   → SeaBIOS
   → GRUB
   → bzImage
   → Linux 6.12.95

第一篇从设备上电开始，沿固件、bootloader、16 位 setup、保护模式、64 位压缩启动桩和
``extract_kernel()`` 连续追踪，直到跳入解压后的正式内核 ``startup_64``。

内容依据
--------

``aiBook`` 的 Linux Kernel Roadmap 表达希望掌握的知识范围。技术细节重新依据 Linux/x86 Boot
Protocol、固定版本源码和可确认的启动行为。旧 ``aiBook/docs/LinuxK`` 只用于对比原内容在哪里绕远、
重复或缺少关键交接。

开始工作
--------

新的对话或助手先阅读：

#. ``AGENTS.md``；
#. `当前状态 <project/STATE.rst>`_；
#. `Linux Kernel 入口 <docs/tracks/linux-kernel/index.rst>`_；
#. 当前正文。