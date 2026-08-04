第035章：dmesg、printk 与运行时证据收集
======================================

本章必须记住
------------

#. ``printk`` 是内核日志基础入口，``pr_*`` 和 ``dev_*`` 宏在它之上表达日志级别与对象上下文。
#. 内核日志的基本路径是：内核调用点 → printk 日志缓冲区 → ``/dev/kmsg`` → ``dmesg``、journald、syslog 或 console。
#. Kernel ring buffer 保存日志记录，console 是实时输出目的地；消息进入缓冲区不等于它已经显示在屏幕或串口上。
#. ``dmesg`` 主要读取内核日志缓冲区，``journalctl -k`` 读取日志服务已经收集和保存的内核消息。
#. Ring buffer 容量有限，系统运行时间较长或日志量过大时，较早记录可能被覆盖。
#. 日志时间戳可能表示启动后的相对时间，也可以由工具转换为墙钟时间；分析时必须记录使用的时间基准。
#. 日志级别从 ``KERN_EMERG`` 到 ``KERN_DEBUG`` 表达严重程度，数值越小表示越紧急。
#. ``pr_err()`` 表示当前操作失败，``pr_warn()`` 表示异常或可疑条件，``pr_info()`` 表示普通状态，``pr_debug()`` 表示调试信息。
#. ``console_loglevel`` 决定哪些级别实时输出到 console，它不决定消息是否进入 ring buffer。
#. 修改 ``/proc/sys/kernel/printk`` 或使用 ``dmesg -n`` 会改变 console 策略；取证前应先保存当前值。
#. ``pr_*_ratelimited()`` 和设备限速宏用于抑制高频重复消息，避免刷屏和覆盖早期证据。
#. ``*_once()`` 宏只报告第一次命中；只看到一条日志不能推断条件只发生了一次。
#. 缺少重复消息可能来自限速、once 语义、调试开关关闭、buffer 覆盖或路径没有实际执行。
#. Dynamic debug 可以按文件、函数、模块和格式字符串选择性打开部分 ``pr_debug()`` 调用点。
#. 打开大量动态调试会增加开销、改变时序并覆盖旧日志，应先缩小模块、函数和复现范围。
#. ``WARN`` 表示内核检测到违反预期的状态，通常打印调用栈；系统可能继续运行，但相关对象和路径未必仍可靠。
#. Oops 通常表示非法访问、异常或严重内核错误；当前任务可能终止，内核也可能因状态损坏继续升级为 panic。
#. Panic 表示内核决定系统不能安全继续运行，并进入停机、重启或 crash dump 策略。
#. ``panic_on_warn``、``panic_on_oops`` 等策略可能把较低级别故障升级成 panic，因此故障结果还受运行配置影响。
#. 调用栈中最靠近故障的相关函数是第一源码入口，上层函数说明执行如何进入该路径。
#. ``function+offset/size [module]`` 中的偏移只有在匹配同一内核、模块、配置和构建产物时才能准确还原源码位置。
#. 分析 Oops 或 panic 必须保存完整日志，而不是只保留最后三行；寄存器、CPU、PID、模块、taint 和前置日志都可能关键。
#. 日志只证明某个打印或报告点执行过，不能单独证明状态在何处被修改，也不能给出并发事件的完整顺序。
#. 一条错误日志中的设备名、动作、返回码和时间可以缩小范围，最终根因仍要结合对象状态、资源路径和调用链。
#. 可靠取证应同时保存内核 release、完整命令行、配置、模块列表、硬件身份和日志原文。
#. 日志应与 ``/proc`` 的系统状态、sysfs 的设备对象、tracefs 的动态路径和 crash dump 的内存现场交叉验证。
#. 清空 ring buffer、重启、改变日志级别或打开调试之前，应先复制和持久化原始证据。

必背路径
--------

日志从源码到用户态：

::

   驱动或核心代码发现事件
   → 调用 dev_err、pr_warn、pr_info 或其它宏
   → printk 写入 kernel ring buffer
   → console 策略决定是否实时显示
   → /dev/kmsg 暴露给用户态
   → dmesg、journald 或 syslog 收集
   → 排查者按对象、时间和级别分析

读取一条错误日志：

::

   保存原始整行与前后上下文
   → 识别时间基准和日志级别
   → 提取设备、模块、函数、动作和错误码
   → 在源码中搜索日志格式字符串
   → 检查调用点的返回路径和对象状态
   → 向前寻找最早相关失败
   → 用 procfs、sysfs 和 tracing 补齐状态与时序

分析 WARN、Oops 或 panic：

::

   保存完整故障块
   → 判断故障类别和升级策略
   → 找最近相关函数及模块
   → 沿调用栈向上识别公共入口
   → 核对 CPU、PID、进程名、taint 和模块列表
   → 使用匹配 vmlinux、System.map 和模块解析符号
   → 检查对象分配、注销、引用和释放路径
   → 结合 KASAN、lockdep 或 crash dump 验证

建立证据时间线：

::

   保存本次启动全部内核日志
   → 筛选目标设备或子系统
   → 标出第一条异常而非只看最后崩溃
   → 对照 sysfs 对象与驱动绑定状态
   → 对照 /proc 计数器和资源状态
   → 使用 tracefs 捕获复现路径
   → 记录所有调试参数和环境变化

必须区分
--------

Ring buffer 与 console
   Ring buffer 保存日志记录；console 只显示满足当前输出策略的部分消息。

日志级别与故障结果
   级别表达调用点意图；系统是否继续运行还受对象状态、错误处理和 panic 策略影响。

WARN、Oops 与 panic
   WARN 报告违反预期；Oops 表示严重执行错误；panic 表示系统停止安全运行。

日志缺失与事件未发生
   限速、once、buffer 覆盖、权限和调试开关都可能造成日志不可见。

调用栈符号与精确源码位置
   函数名提供路径入口；精确行号要求匹配同一构建的符号和二进制。

报告点与根因
   日志显示代码在哪里发现问题；根因可能发生在更早的状态修改、资源失败或并发窗口。

一句话结论
----------

``printk`` 把内核事件写成有限容量的运行时日志，``dmesg`` 负责读取；可靠诊断必须保存完整时间线，并把报告点与对象状态、源码路径和 tracing 证据结合起来。

来源
----

* AIBook 书籍：LinuxK；
* AIBook 章节：Chapter 35，dmesg, printk, and Runtime Evidence Collection；
* 源文件：``docs/LinuxK/Part_07_Observability_Interfaces_procfs_sysfs_debugfs_tracefs_and_dmesg/Chapter_035_dmesg_printk_and_Runtime_Evidence_Collection.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_07_Observability_Interfaces_procfs_sysfs_debugfs_tracefs_and_dmesg/Chapter_035_dmesg_printk_and_Runtime_Evidence_Collection.md>`_。