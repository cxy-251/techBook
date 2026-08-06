第166章：Kernel Command Line Parameters 与早期运行控制
========================================================

本章必须记住
------------

#. Kernel Command Line 是 Bootloader 在用户态出现前交给内核的早期控制字符串。
#. 同一条命令行可同时承载核心内核参数、内建驱动参数、模块参数以及传给第一个用户态 ``init`` 的参数和环境变量。
#. 启动参数的首要判断不是“值是什么”，而是“由哪个阶段、哪个参数表、哪个子系统消费”。
#. Bootloader 负责传递字符串，不负责证明内核识别或成功执行了其中每个参数。
#. ``/proc/cmdline`` 只能证明当前内核收到的命令行内容，不能证明某个参数已被目标代码接受并产生预期效果。
#. 启动参数早于 systemd、sysctl 配置、模块加载脚本和常规诊断服务，因此能控制普通用户态工具尚未出现时的行为。
#. 早期控制台、内存布局、CPU 特性、IOMMU、ACPI、根文件系统、安全模块和驱动探测等问题常需要通过启动参数干预。
#. 稳定主线是：Bootloader 字符串 → 架构保存 → Early Parse → 通用参数 Parse → Initcall/Driver → Init 参数。
#. 命令行长度存在架构和版本边界，超长或被 Bootloader 截断的字符串可能造成尾部参数丢失。
#. 参数重复时采用首个、最后一个、累计或回调多次的语义取决于具体实现，不能统一假设“最后一个覆盖”。
#. 参数名、取值、默认值、废弃状态和架构支持必须以目标内核版本的参数文档与源码为准。
#. ``early_param`` 用于必须在普通初始化设施完整可用前处理的参数。
#. Early 参数常服务于早期 Console、架构交接、内存、日志、CPU 或平台选择。
#. ``__setup`` 注册传统 Setup 参数处理函数，通常在 Early 阶段之后的启动解析中消费。
#. ``core_param`` 把核心内核参数接入通用 Kernel Parameter 机制。
#. ``module_param`` 把驱动或子系统变量接入模块参数机制；驱动内建时也可能由 Kernel Command Line 传值。
#. 四类宏的稳定差异是拥有者、解析时机、参数元数据和运行时可见性，而不是名称风格。
#. ``early_param`` 与 ``__setup`` 常通过特殊 Linker Section 建立参数表，启动代码遍历这些表调用处理函数。
#. ``core_param`` 与 ``module_param`` 通常通过 ``kernel/params.c`` 一类通用解析路径完成类型转换和赋值。
#. 参数处理函数返回值具有消费语义，错误返回或未消费可能产生 Unknown Parameter 日志或转入其它路径。
#. 解析成功只说明输入形式被接受；子系统后续初始化仍可能因硬件、配置或资源失败。
#. 内建驱动参数通常采用 ``module_name.parameter=value`` 的命令行形式。
#. 可加载模块在 ``modprobe``/``insmod`` 时接收参数；同一个驱动编译形态不同会改变有效传参入口。
#. 把参数写入 ``/etc/modprobe.d`` 不会影响已经内建并在启动阶段初始化的驱动。
#. 把内建驱动参数写成无模块名前缀，可能被解释为未知内核参数或错误地传给 ``init``。
#. 模块名中的连字符和下划线可能存在规范化规则，精确匹配应查看目标模块元数据和参数解析实现。
#. 命令行在 ``--`` 之前主要由内核解析；``--`` 之后通常作为参数传给用户态 ``init``。
#. 未被内核识别且不含点号的普通参数可能成为 ``init`` 参数；带 ``=`` 的形式可能进入 ``init`` 环境。
#. 含点号的未知参数通常按模块参数候选处理，不应依赖它必然传给用户态。
#. 因此“启动参数存在”与“第一个用户态进程收到该参数”必须分别验证。
#. ``init=`` 或相关参数可选择替代的第一个用户态程序，适合恢复和最小化启动实验。
#. ``rdinit=`` 一类参数面向 Initramfs 阶段，和最终 Rootfs 上的 ``init=`` 不是同一入口。
#. ``root=``、``rootfstype=``、``rootflags=`` 控制根文件系统定位与挂载，具体设备发现仍依赖驱动和 Initramfs。
#. 根设备参数正确不表示驱动已内建或 Initramfs 包含必要模块。
#. ``earlycon`` 的目标是在普通 Console 驱动完整注册前提供早期日志输出。
#. ``earlycon`` 具有强平台依赖，可能通过固件描述、SPCR、Device Tree 或显式 UART 参数建立。
#. 早期 Console 成功不表示后续正式 Console 也会注册；切换阶段可能出现日志空窗或输出到不同设备。
#. ``console=`` 选择正式 Console，多个 ``console=`` 的输出与首选终端语义需按内核文档确认。
#. ``loglevel=`` 控制 Console 输出阈值，不决定 Ring Buffer 中是否生成所有消息。
#. 提高 ``loglevel`` 可增加启动证据，也会增加串口输出延迟和日志噪声。
#. ``log_buf_len=`` 可扩大 Printk Ring Buffer，但需要在相应早期阶段生效。
#. ``ignore_loglevel`` 一类参数可强制更多消息进入 Console，适合短期启动诊断，不适合长期常态运行。
#. ``initcall_debug`` 为 Initcall 进入、返回和耗时提供时间线证据。
#. Initcall 最后打印的位置不一定就是根因；函数可能异步启动工作，后续卡死发生在 Worker、IRQ 或设备完成路径。
#. ``initcall_debug`` 增加证据，不自动定位锁死、硬件等待或错误回滚问题。
#. ``panic=N`` 控制 Panic 后等待与重启策略；正数、0、负数语义应按目标文档确认。
#. Panic 自动重启有助于无人值守恢复，也可能覆盖现场或造成 Crash Loop。
#. Kdump 场景中，Panic 策略必须与 Crash Kernel、转储时间和 Watchdog 配合。
#. ``nomodeset`` 常用于阻止图形驱动执行 Kernel Mode Setting，作为黑屏问题的回退测试。
#. ``nomodeset`` 能帮助区分图形接管问题，不是图形故障的长期修复。
#. 关闭 Mode Setting 可能失去硬件加速、高分辨率、外接显示和现代 DRM 功能。
#. 驱动黑名单、禁用特定设备或关闭某项硬件特性，应优先使用对应子系统正式参数，而不是盲目加入通用字符串。
#. ``module_blacklist=``、``modprobe.blacklist=`` 等名字可能作用于不同阶段或用户态工具，必须确认内核与 Initramfs 行为。
#. 内核参数不能替代 Initramfs 内的模块加载策略；早期用户态可能再次加载或配置设备。
#. CPU 参数可能影响核心数、Idle、Frequency、Mitigation、NUMA 或调度初始化，风险范围可覆盖整机。
#. 内存参数可能改变可用内存、Crash Kernel、Huge Page、NUMA 或分配器布局，错误值可能让系统无法启动。
#. IOMMU 参数可能改变 DMA 地址转换、隔离与设备兼容性，不能只以“性能更快”判断。
#. 安全参数可能改变 LSM、Lockdown、Module Signature、IMA/EVM、随机化或缓解措施，临时绕过会扩大攻击面。
#. ``mitigations=off`` 一类参数会改变安全边界，应视为受控性能实验，而不是普通调优。
#. 参数影响范围可分为：启动一次性状态、初始化后固定状态、可在运行时继续修改的参数。
#. 一个参数在 sysfs 中可见，不表示启动期写入后的全部硬件决策可以运行时重做。
#. 一次性早期参数通常无法在系统运行后安全撤销，只能修改 Boot Entry 并重启验证。
#. 启动参数的持久化由 Bootloader、Boot Entry、Kernel Stub 或发行版配置管理，不由内核自身保存。
#. 修改 ``/proc/cmdline`` 不可能改变当前命令行，它是只读运行证据。
#. GRUB、systemd-boot、UKI、U-Boot 等管理方式不同，参数实际来源必须从当前 Boot Chain 验证。
#. 自动生成 Boot Entry 的发行版可能覆盖手工编辑文件，长期修改应进入正式配置源。
#. 恢复测试应先复制现有 Boot Entry，保留一个已知可启动的回退项。
#. 远程主机修改启动参数前必须准备 Console/BMC/Serial 和自动回滚，不能只依赖 SSH。
#. 参数实验应一次改变一个关键变量，记录旧命令行、新命令行、内核版本、Boot ID 和结果。
#. 启动失败时应收集固件/Bootloader 输出、Early Console、Printk、Pstore、Kdump 和用户态 Journal，不只看一层日志。
#. ``dmesg`` 中的 ``Kernel command line:``、Unknown Parameter、Deprecated Parameter 等消息是解析证据。
#. 某些敏感参数可能被日志隐藏或只在早期出现，运行后证据需结合配置和源码。
#. Secure Boot 或 Lockdown 可限制某些参数和运行时控制，即使命令行字符串存在。
#. Firmware、Hypervisor 或云平台可能注入、重写或过滤命令行，来宾内看到的结果应以 ``/proc/cmdline`` 为准。
#. Kexec 启动可以使用不同于首次启动的命令行，排障必须记录当前 Boot Generation。
#. 容器通常共享宿主 Kernel Command Line，容器内看到的 procfs 可能被隐藏或重新挂载，但不能独立修改宿主启动参数。
#. 读源码时先搜索参数字符串，再定位注册宏、处理函数、变量和最终使用点。
#. 只找到参数声明不足以说明行为，必须追踪变量在哪个 Initcall、Probe 或运行路径中读取。
#. 参数处理回调可能立即产生副作用，而不仅仅是写变量。
#. 自定义 ``param_ops`` 或 Setup Handler 可能执行校验、资源分配和状态转换。
#. 参数解析发生在特定锁和启动上下文中，处理函数不能假设完整调度、设备模型或文件系统已经可用。
#. Early Handler 尤其不能调用尚未初始化的普通内核服务。
#. 参数废弃时内核可能保留兼容别名、输出警告或静默忽略，升级后应检查日志。
#. 同名参数在不同版本的语义可能变化，不能把旧发行版经验直接套到新内核。
#. 稳定排障顺序是：确认当前命令行 → 分类参数拥有者与阶段 → 查解析证据 → 查最终状态 → 对照故障时间线。
#. 黑屏故障可按：Early Console → Initcall → DRM/PCI Probe → Mode Setting → 用户态图形服务分层。
#. Rootfs 故障可按：设备驱动 → Initramfs → Root 参数 → 文件系统驱动 → Mount 错误分层。
#. 启动卡死可通过减少硬件路径、提高日志、启用 Initcall 证据和二分参数定位，但每次只改一个变量。
#. 参数成功规避问题后，应回到对应源码、驱动日志和硬件状态找根因，而不是永久保留宽泛禁用项。
#. 启动参数属于稳定 UAPI 的程度因参数而异；文档化参数通常比调试/实验参数稳定。
#. 精确参数表、处理顺序、宏实现和 Init 传参规则具有内核版本、架构和发行版差异。
#. 稳定源码阅读顺序是：Bootloader String → Arch Save → Early Table → Generic Params → Module Params → Initcall Use → Userspace Handoff。

必背路径
--------

启动参数主路径：

::

   Firmware / Bootloader 选择 Kernel 与 Boot Entry
   → 把 Command Line 放入架构启动协议
   → 架构代码保存原始字符串
   → Early 参数表解析 early_param
   → 通用解析处理 __setup/core_param/module_param
   → Initcall 与 Driver 读取已建立状态
   → 剩余参数/环境交给第一个用户态 init

黑屏启动诊断：

::

   保留可回退 Boot Entry
   → 加入 earlycon 与合适 console
   → 提高 loglevel / 扩大 log buffer
   → 启用 initcall_debug
   → 单独测试 nomodeset 或目标驱动参数
   → 收集 DRM/PCI/Initcall 日志
   → 确定最早偏离预期的阶段

参数源码定位：

::

   搜索参数字符串
   → 找到 early_param/__setup/core_param/module_param 声明
   → 确认解析阶段与类型
   → 阅读 Handler/param_ops
   → 查找变量全部引用
   → 定位最终影响的 Initcall、Probe 或运行路径
   → 验证运行证据

安全修改启动项：

::

   记录当前 /proc/cmdline 与 Boot Entry
   → 创建独立测试 Entry
   → 一次修改一个参数
   → 准备 Serial/BMC/本地 Console
   → 重启并记录 Boot ID、日志与结果
   → 成功后再更新正式配置源
   → 保留已知可启动回退项

必须区分
--------

* 参数出现在 ``/proc/cmdline`` 与参数生效：前者只证明字符串被传入；后者需要解析日志、子系统状态和实际行为证明。
* ``early_param`` 与普通参数：Early 参数在基础设施尚未完整初始化时处理；普通参数在后续通用解析阶段处理。
* 内建驱动参数与可加载模块参数：内建驱动主要从 Kernel Command Line 取值；可加载模块可由 ``modprobe``/``insmod`` 传值。
* Kernel 参数与 Init 参数：内核消费自己的控制项；未消费部分及 ``--`` 后内容可进入第一个用户态进程。
* 临时启动规避与根因修复：``nomodeset``、禁用设备等可帮助定位，长期方案应修复驱动、固件、配置或硬件问题。

一句话结论
----------

Kernel Command Line 是用户态出现前的分阶段控制面：必须先确认谁在何时消费参数，再用最终内核状态证明它真正生效。
