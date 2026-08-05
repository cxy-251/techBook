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

Part 5：启动序列、Initcall 与早期内核初始化
------------------------------------------

* `第021章：从固件到 Bootloader <021-from-firmware-to-bootloader.rst>`_；
* `第022章：内核解压与早期架构初始化 <022-kernel-decompression-and-early-architecture-setup.rst>`_；
* `第023章：内核命令行与早期参数 <023-kernel-command-line-and-early-parameters.rst>`_；
* `第024章：Initcall 层级与子系统初始化 <024-initcall-levels-and-subsystem-initialization.rst>`_；
* `第025章：调试 Linux 早期启动故障 <025-debugging-early-boot-failures.rst>`_。

Part 6：内核对象、生命周期、引用与错误路径
------------------------------------------

* `第026章：内核对象是具有生命周期的 C 结构体 <026-kernel-objects-as-c-structures-with-lifetimes.rst>`_；
* `第027章：引用计数与所有权转移 <027-reference-counting-and-ownership-transfer.rst>`_；
* `第028章：资源申请与释放顺序 <028-resource-acquisition-and-release-ordering.rst>`_；
* `第029章：对象注册、查找与销毁 <029-object-registration-lookup-and-teardown.rst>`_；
* `第030章：失败路径是内核设计的真实检验 <030-failure-paths-as-the-real-test.rst>`_。

Part 7：可观测接口：procfs、sysfs、debugfs、tracefs 与 dmesg
-----------------------------------------------------------

* `第031章：procfs 是进程与内核状态的运行时视图 <031-procfs-runtime-view.rst>`_；
* `第032章：sysfs 是设备与对象模型接口 <032-sysfs-device-and-object-model.rst>`_；
* `第033章：debugfs 是开发者控制的调试面 <033-debugfs-developer-debug-surface.rst>`_；
* `第034章：tracefs 与内核追踪接口 <034-tracefs-kernel-tracing-interface.rst>`_；
* `第035章：dmesg、printk 与运行时证据收集 <035-dmesg-printk-runtime-evidence.rst>`_。

Part 8：用户态—内核态边界与系统调用路径
--------------------------------------

* `第036章：用户代码怎样进入内核 <036-user-code-entry-into-kernel.rst>`_；
* `第037章：系统调用表、入口代码与 ABI 稳定性 <037-syscall-tables-entry-and-abi-stability.rst>`_；
* `第038章：跨越用户态与内核态边界复制数据 <038-copying-data-across-user-kernel-boundary.rst>`_；
* `第039章：文件描述符、句柄与内核对象 <039-file-descriptors-handles-and-kernel-objects.rst>`_；
* `第040章：失败、errno 与边界诊断 <040-failure-errno-and-boundary-diagnostics.rst>`_。

Part 9：进程、线程、task_struct 与执行上下文
--------------------------------------------

* `第041章：task_struct 是 Linux 内核的任务对象 <041-task-struct-as-kernel-process-object.rst>`_；
* `第042章：fork、clone 与 exec 的进程创建语义 <042-process-creation-fork-clone-exec.rst>`_；
* `第043章：线程、线程组与共享资源 <043-threads-thread-groups-shared-resources.rst>`_；
* `第044章：进程状态、睡眠、唤醒与信号 <044-process-states-sleep-wakeup-signals.rst>`_；
* `第045章：进程、中断与内核线程执行上下文 <045-execution-contexts-process-interrupt-kernel-thread.rst>`_。

阅读方式
--------

按编号直接阅读和记忆即可。正文不设置问题、练习和互动环节。需要完整推导、源码例子或实验时，
使用每章末尾的 AIBook 来源链接。
