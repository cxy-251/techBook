项目状态
========

最后更新
--------

2026-07-11

当前任务
--------

仓库当前只写 Linux Kernel。

正在编写：

``LK-BOOT-001：设备上电后，x86-64 Linux 内核怎样被装入并完成解压？``

主线固定为：

::

   x86-64
   → SeaBIOS
   → GRUB
   → bzImage
   → Linux 6.12.95

正文范围
--------

从设备上电开始，连续追踪到压缩启动桩完成解压，并跳入
``arch/x86/kernel/head_64.S:startup_64``。

当前正文覆盖：

* 固件取得控制权；
* SeaBIOS 选择启动设备；
* GRUB 读取 ``bzImage`` 与 Linux boot protocol header；
* setup 区域和受保护模式负载的装入；
* ``header.S:start_of_setup``；
* ``main.c:main`` 与 ``boot_params``；
* 实模式到保护模式；
* 压缩启动桩的 ``startup_32`` 与 ``startup_64``；
* ``extract_kernel()``；
* 跳入解压后的正式内核入口。

已经完成
--------

* 确认旧 Roadmap 在进入启动链前安排了 20 章世界观、阅读方法、源码导航、内核 C 和构建内容；
* 将 Linux 开篇改为按真实启动时间线直接叙述；
* 建立第一篇 RST 初稿；
* 撤下原来的 ``write()`` 系统调用开场。

当前下一步
----------

只审阅和修改 ``docs/tracks/linux-kernel/01-power-on-to-decompression.rst``，重点检查启动环节是否缺失、
源码交接是否准确、细节是否足够连续。当前正文稳定后再决定下一篇。