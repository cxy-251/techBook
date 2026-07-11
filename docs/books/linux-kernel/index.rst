Linux Kernel 源码阅读
=====================

第一卷范围已经固定：ARM64 启动入口、MMU 与虚拟地址切换、通用初始化、initcall、用户空间 init、``read()`` 系统调用与 VFS。

当前状态：内容计划已经 frozen，source contract 尚未锁定，章节生成保持 blocked。

第一章：``LK-BOOT-001``——ARM64 Linux 内核镜像从哪个入口开始执行？

``read()`` 与 VFS 位于第一卷后半部分，不作为起始章节。

.. toctree::
   :maxdepth: 2

   reading-contract
