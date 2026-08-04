第025章：调试 Linux 早期启动故障
================================

本章必须记住
------------

#. 早期启动故障最困难的地方是：系统失败时，普通日志、磁盘、网络、图形界面和用户态工具可能都还没有建立。
#. 早期启动排查的第一目标不是立即解释根因，而是先恢复最小可观测性，让内核留下可靠证据。
#. 没有屏幕输出不能直接证明内核没有执行；可能只是 console 没有注册、日志级别太低或输出设备参数错误。
#. ``printk()`` 先把消息写入内核日志缓冲区，消息是否立即出现在串口或屏幕还取决于 console 注册和日志级别。
#. 用户态尚未启动时不能依赖 ``dmesg``、``journalctl`` 或磁盘日志；需要使用 early console、串口、固件输出或持久化崩溃记录。
#. 排查时应把启动拆成阶段：固件与 bootloader、镜像解压或架构入口、``start_kernel()``、早期参数、内存与调度基础、initcall、initramfs 与根文件系统、用户态 init。
#. 最后一个明确成功的阶段和第一个缺失的阶段，比“卡死了”更接近可验证的故障范围。
#. Bootloader 显示已经加载镜像，只能证明文件装载阶段推进，不能证明内核入口、解压和页表已经成功。
#. 出现 ``Linux version`` 或 Linux banner，说明内核已经进入可打印的早期路径。
#. 出现 ``Kernel command line``，说明启动参数已经被内核保存并打印，但不证明全部参数都正确生效。
#. 出现 ``earlycon`` 或 ``bootconsole enabled``，说明早期 console 注册留下了证据，但后续普通 console 仍可能接管失败。
#. ``earlycon`` 在普通 tty 和 console 驱动之前建立低依赖输出通道，常以串口、MMIO UART、设备树 stdout-path 或 ACPI SPCR 为依据。
#. ``console=ttyS0,115200n8`` 指定后续普通串口 console；``earlycon`` 与 ``console=`` 解决的阶段不同，常需要同时配置。
#. ``loglevel=8`` 和 ``ignore_loglevel`` 可以增加控制台可见日志，``log_buf_len=`` 可以扩大日志缓冲区。
#. ``initcall_debug`` 会记录 initcall 的开始、结束、返回值和耗时，可用于定位最后进入或长时间未返回的初始化函数。
#. 打开更多日志可能改变时序和性能，尤其会影响并发、竞态和超时问题；调试结论要记录参数变化。
#. 读取 initcall 日志时，应区分“调用后尚未返回”“返回负错误码”“返回成功但后续依赖失败”和“耗时异常长”。
#. Initcall 返回错误不一定立即停止启动；真正影响取决于该功能是否是后续根文件系统、控制台或设备链的必要依赖。
#. ``VFS: Unable to mount root fs`` 表示内核已经推进到根文件系统挂载阶段，问题通常集中在 ``root=``、文件系统支持、存储驱动、设备命名和 initramfs。
#. 根文件系统所需的存储控制器、总线和文件系统如果构建成模块，必须能从 initramfs 中加载；最终根文件系统本身尚未挂载时不能从那里取得这些模块。
#. ``unknown-block(major,minor)`` 提供内核当前解析到的根设备线索，应结合设备节点、驱动和分区识别继续判断。
#. ``Waiting for root device`` 常表示内核正在等待目标设备出现，需要检查 ``root=``、``rootwait``、驱动、固件和设备枚举。
#. ``No working init found`` 或无法执行 init，说明根文件系统路径已经比早期架构初始化更进一步，问题集中在 init 文件、权限、解释器、动态链接器和根文件系统内容。
#. ``rdinit=`` 用于指定 initramfs 中的 init，``init=`` 用于指定最终根文件系统中的 init；两者可以帮助隔离故障阶段。
#. ``init=/bin/sh`` 只有在最终根文件系统已挂载且 shell 及其依赖可执行时才有诊断价值。
#. 串口日志应由另一台机器、BMC SOL、虚拟机控制台或文件捕获，避免机器重启后证据丢失。
#. pstore、ramoops、kdump 等机制可以保存部分崩溃证据，但它们需要提前配置并且可用阶段不同，不能作为所有极早期故障的默认条件。
#. 调试早期启动时应保留一个已知可启动的内核和 bootloader 条目，避免单次错误配置使系统失去恢复入口。
#. 每次只改变少量启动参数或一个构建变量，并保存完整命令行和日志，才能判断哪项修改改变了结果。
#. 早期启动调试的本质是阶段化二分：先恢复输出，再定位最后成功阶段，最后把阶段映射回对应源码、配置和启动材料。

必背路径
--------

恢复最小可观测性：

::

   保留 bootloader 自身输出
   → 启用平台匹配的 earlycon
   → 同时配置后续 console
   → 提高 loglevel 并启用 ignore_loglevel
   → 扩大 log buffer
   → 启用 initcall_debug
   → 使用串口、BMC 或虚拟机控制台完整捕获日志

启动阶段定位：

::

   bootloader 是否加载并跳转
   → 是否出现解压或架构入口证据
   → 是否出现 Linux banner
   → 是否打印 Kernel command line
   → early console 是否注册
   → 内存、调度和 SMP 基础是否推进
   → initcall 最后调用和返回的是谁
   → initramfs 是否准备完成
   → 根文件系统是否挂载
   → 用户态 init 是否成功执行

Initcall 故障判断：

::

   日志出现 calling foo_init
   → 检查是否出现 returned foo_init
   → 无返回则检查死锁、等待和硬件超时
   → 返回负值则追踪失败资源与必要依赖
   → 返回成功则检查异步工作、probe 和后续消费者
   → 结合函数所在 level 与 provider 依赖定位

根文件系统故障路径：

::

   检查 root= 指向的设备
   → 检查存储总线与控制器驱动
   → 检查分区和块设备是否出现
   → 检查目标文件系统是内建还是模块
   → 模块形态时检查 initramfs 是否包含模块与依赖
   → 检查 rootfstype、rootflags、rootwait 等参数
   → 检查最终根目录中的 init 和动态链接器

安全的调试迭代：

::

   保留已知可启动内核
   → 复制 bootloader 条目
   → 每次只改一组参数
   → 捕获完整日志
   → 标出最后成功阶段
   → 回到对应源码与配置验证
   → 记录结果后再进行下一次修改

必须区分
--------

消息产生与消息可见
   ``printk`` 可能已经产生记录；console、loglevel 和设备状态决定观察者是否立即看到它。

``earlycon`` 与普通 console
   ``earlycon`` 服务普通驱动就绪前的输出；``console=`` 指定后续正式控制台。

启动卡死与输出卡死
   机器可能仍在执行但没有可见输出；必须先验证输出通道，再判断执行是否停止。

Initcall 返回成功与设备可用
   Initcall 成功可能只完成驱动注册；设备匹配、probe、异步初始化和资源获取仍可能失败。

根文件系统失败与用户态 init 失败
   根文件系统失败表示尚未得到最终根目录；init 失败表示根目录已更接近可用，但 PID 1 无法执行。

一句话结论
----------

早期启动调试不是从错误文本猜根因，而是先恢复最小输出，确定最后成功的启动阶段，再把阶段映射到对应镜像、参数、initcall、根文件系统或 init 路径。

来源
----

* AIBook 书籍：LinuxK；
* AIBook 章节：Chapter 25，Debugging Early Boot Failures；
* 源文件：``docs/LinuxK/Part_05_Boot_Sequence_Initcalls_and_Early_Kernel_Initialization/Chapter_025_Debugging_Early_Boot_Failures.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_05_Boot_Sequence_Initcalls_and_Early_Kernel_Initialization/Chapter_025_Debugging_Early_Boot_Failures.md>`_。
