Linux Kernel 必背课本
=====================

本目录与 AIBook 的 ``docs/LinuxK`` 一一对应。AIBook 是完整教材，这里只保留每章中稳定、必须掌握、
可以直接记忆的知识。

Part 1：内核世界观与工程心智模型
---------------------------------

* `第001章：Linux 内核资源管理模型 <001-linux-kernel-resource-management-model.rst>`_；
* `第002章：为什么 Linux 内核源码难读 <002-why-linux-kernel-source-is-difficult.rst>`_；
* `第003章：Linux 内核的核心设计取舍 <003-core-kernel-design-forces.rst>`_；
* `第004章：Linux 内核的四条核心路径 <004-four-great-kernel-paths.rst>`_；
* `第005章：怎样学习 Linux 内核源码 <005-how-to-read-linux-kernel-handbook.rst>`_。

Part 2：源码树与代码导航
------------------------

* `第006章：Linux 内核源码树的结构 <006-shape-of-kernel-source-tree.rst>`_；
* `第007章：怎样在巨大源码库中找到入口 <007-finding-kernel-entry-points.rst>`_；
* `第008章：怎样阅读 Linux 内核数据结构 <008-reading-kernel-data-structures.rst>`_；
* `第009章：怎样结合状态追踪内核调用链 <009-following-call-chains-with-state.rst>`_；
* `第010章：建立个人内核源码阅读工作流 <010-personal-kernel-reading-workflow.rst>`_。

Part 3：内核 C 语法、核心 API 与运行时约束
-----------------------------------------

* `第011章：Linux 内核 C 的运行时约束 <011-kernel-c-runtime-constraints.rst>`_；
* `第012章：Linux 内核核心数据结构 <012-core-kernel-data-structures.rst>`_；
* `第013章：Linux 内核错误处理与返回约定 <013-kernel-error-handling.rst>`_；
* `第014章：Linux 内核日志与诊断语法 <014-kernel-logging-and-diagnostics.rst>`_；
* `第015章：Linux 内核代码风格、评审与可维护性 <015-kernel-coding-style-and-maintainability.rst>`_。

Part 4：Kconfig、Kbuild、模块与内核镜像
--------------------------------------

* `第016章：使用 Kconfig 配置 Linux 内核 <016-kernel-configuration-with-kconfig.rst>`_；
* `第017章：使用 Kbuild 构建 Linux 内核 <017-kernel-build-system-with-kbuild.rst>`_；
* `第018章：Linux 可加载内核模块 <018-loadable-kernel-modules.rst>`_；
* `第019章：Linux 内核镜像、符号与 initramfs <019-kernel-images-symbols-and-initramfs.rst>`_；
* `第020章：建立可复现的 Linux 内核构建 <020-reproducible-kernel-build.rst>`_。

阅读方式
--------

按编号直接阅读和记忆即可。正文不设置问题、练习和互动环节。需要完整推导、源码例子或实验时，
使用每章末尾的 AIBook 来源链接。
