第025章：调试 Linux 早期启动故障
================================

核心知识点
----------

早期启动失败首先是可观测性问题
   系统尚未完整建立时，普通终端、磁盘日志、网络、图形界面和用户态工具可能都不可用。排查的第一目标是让内核留下最小可靠证据，而不是立即猜测根因。

启动必须按阶段定位
   启动链可以划分为固件与 Bootloader、镜像解压或架构入口、``start_kernel()``、早期参数、内存与调度基础、initcall、initramfs 与根文件系统、用户态 init。最后成功阶段决定下一步检查范围。

消息产生与消息可见是两件事
   ``printk()`` 可以先把记录写入 ring buffer；消息是否出现在屏幕或串口，还取决于 console 是否注册、日志级别和设备状态。没有输出不能直接证明内核没有执行。

Early console 恢复最低依赖输出
   ``earlycon`` 在普通 tty 与 console 驱动准备前建立输出通道；``console=`` 指定后续正式控制台。串口、BMC SOL 和虚拟机控制台适合跨重启保存完整早期日志。

调试参数用于放大阶段证据
   ``loglevel=8``、``ignore_loglevel`` 和 ``log_buf_len=`` 增强日志可见性；``initcall_debug`` 记录 initcall 的调用、返回值和耗时。增加日志可能改变时序，必须记录启用的参数。

最后一条成功日志比“卡死”更有价值
   Linux banner、Kernel command line、bootconsole、initcall 调用与返回、根文件系统错误和 init 执行错误分别对应不同启动边界。应寻找第一个缺失阶段，而不是只搜索最后一条错误文字。

Initcall 日志要结合返回和依赖判断
   只有 ``calling foo_init`` 而没有返回，可能表示死锁、等待或硬件超时；返回负值表示当前初始化失败；返回成功仍不保证 probe、异步工作和消费者已经完成。

根文件系统与 init 失败属于后期边界
   ``Unable to mount root fs``、``Waiting for root device`` 常指向 ``root=``、存储驱动、文件系统和 initramfs；``No working init found`` 表示路径已经更接近用户态，需要检查 init、解释器、动态链接器和根文件系统内容。

关键路径
--------

恢复最小可观测性：

::

   保留 Bootloader 输出
   → 配置平台匹配的 earlycon
   → 同时配置后续 console
   → 提高 loglevel 并启用 ignore_loglevel
   → 扩大 log buffer
   → 启用 initcall_debug
   → 通过串口、BMC 或虚拟机控制台捕获完整日志

阶段化定位：

::

   Bootloader 是否完成跳转
   → 是否出现解压或架构入口证据
   → 是否出现 Linux banner
   → 是否打印 Kernel command line
   → early console 是否注册
   → 内存与调度基础是否完成
   → 最后一个 initcall 是否返回
   → initramfs 与根文件系统是否成功
   → 用户态 init 是否执行

概念辨析
--------

启动卡死与输出卡死
   启动卡死表示执行没有继续推进；输出卡死可能只是 console 未建立或日志不可见，机器仍在运行。

``earlycon`` 与普通 console
   ``earlycon`` 服务普通驱动就绪前的最低依赖输出；``console=`` 指定后续正式控制台。

Initcall 返回成功与设备可用
   Initcall 成功可能只完成驱动或框架注册；设备匹配、probe、异步初始化和资源获取仍可能失败。

根文件系统失败与用户态 init 失败
   根文件系统失败表示最终根目录尚未建立；init 失败表示根目录已更接近可用，但 PID 1 无法执行。

调试参数与原始复现条件
   调试参数增加证据，也可能改变时序和性能；结论必须注明参数变化，不能把调试环境直接等同于原始环境。

本章结论
--------

早期启动调试的核心是先恢复最低可观测性，再确定最后成功阶段，并把该阶段映射回对应镜像、参数、initcall、根文件系统或 init 路径。