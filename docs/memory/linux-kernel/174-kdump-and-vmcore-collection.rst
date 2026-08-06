第174章：kdump 与 vmcore 收集
============================

本章必须记住
------------

#. Kdump 的目标是在运行内核已经 Panic、严重 Oops、Hard Lockup 或内存破坏后，使用预先隔离的第二内核保存崩溃现场。
#. 崩溃后的分析能力主要由崩溃前的配置决定；系统已经失控后再临时建立可靠取证路径通常来不及。
#. Kdump 的三个核心对象是 ``crashkernel=`` 预留内存、通过 Kexec 预加载的 Dump-capture Kernel，以及第二内核中的 ``/proc/vmcore``。
#. 第一内核正常启动时预留一段物理内存，普通页分配器不能使用它；这段内存用于容纳 Capture Kernel、Initramfs 和必要数据。
#. ``kexec -p`` 一类路径把 Crash Kernel 预加载到保留区；Panic 时第一内核通过 ``crash_kexec()`` 等路径切换到第二内核。
#. Dump-capture Kernel 不是用来恢复业务，而是运行一个尽量小、依赖尽量少的收集环境。
#. 第二内核通过 ``/proc/vmcore`` 读取第一内核崩溃时的内存视图，并保存到本地磁盘、远端网络或其它目标。
#. ``/proc/vmcore`` 通常表现为 ELF Core 风格文件；它不是第二内核自己的普通内存快照。
#. Vmcore 包含哪些页取决于崩溃内存布局、架构、Kdump、Makdumpfile 过滤级别和收集是否完整。
#. 完整 Vmcore 价值最高、体积也最大；过滤/压缩可减少空间，但可能删除后续分析需要的对象页面。
#. 取证设计必须在“文件大小”和“保留足够内核对象”之间做明确权衡。
#. Panic 路径只说明系统进入崩溃处理，不保证 Vmcore 一定产生。
#. Vmcore 成功依赖：Crashkernel 预留成功、Crash Kernel 已加载、触发路径可进入 Kexec、第二内核能启动、目标存储/网络可用、用户态收集脚本成功。
#. ``/proc/cmdline`` 出现 ``crashkernel=`` 只证明字符串存在，不证明物理内存实际预留。
#. ``/proc/iomem`` 中的 Crash Kernel 区域是预留状态的重要证据。
#. ``/sys/kernel/kexec_crash_loaded`` 等接口可说明当前是否加载了 Crash Kernel，精确路径和语义依内核版本与发行版工具而定。
#. Crashkernel 内存大小必须覆盖第二内核、Initramfs、驱动、用户态工具、网络/存储栈和收集过程中需要的内存。
#. 预留过小会导致第二内核启动失败、OOM、驱动初始化失败或收集过程中崩溃。
#. 预留过大则减少生产内核可用内存，尤其在小内存和低地址受限平台上影响明显。
#. ``crashkernel=SIZE``、范围形式、High/Low 形式和固定地址形式具有架构与版本差异，应使用目标发行版推荐配置。
#. 某些设备和架构要求低端内存、32-bit DMA 或特殊保留区，不能只按总内存比例选择大小。
#. Kexec 和 Kdump 依赖内核配置、签名验证、Secure Boot、Lockdown 和发行版策略。
#. Secure Boot 环境下 Crash Kernel、Initramfs 或 Kexec Image 可能需要受信签名，加载失败要查看明确日志。
#. Dump-capture Kernel 应尽量减少 CPU、驱动和并发复杂度，常见会限制 CPU 数、使用 ``irqpoll`` 或 ``reset_devices`` 等参数。
#. 这些参数是为收集可靠性服务，不应直接复制到普通生产内核命令行。
#. 崩溃时设备可能处于 DMA、IRQ、Firmware 或 Queue 的异常状态；第二内核重新初始化设备并不总能成功。
#. ``reset_devices`` 只是向驱动表达重置需求，不能保证所有硬件、Firmware 和总线都能恢复到干净状态。
#. 存储栈本身是崩溃源时，本地磁盘保存可能失败或进一步破坏数据，应准备远程或独立设备路径。
#. 网络远程保存依赖 NIC、驱动、链路、地址、Route、认证和目标服务器；其配置必须包含在 Capture Initramfs 中并做真实测试。
#. 本地保存必须检查目标文件系统、空间、Mount、加密、LVM/MD/DM 路径和写入权限。
#. 完整内存镜像可能包含密钥、用户数据、凭证、网络内容和商业机密，Vmcore 是高敏感资产。
#. Vmcore 存储、传输、访问控制、保留周期和删除必须按安全事件数据管理。
#. Makdumpfile 可以过滤、压缩或转换 Vmcore，但过滤策略必须记录并与后续 Crash 工具兼容。
#. 只保留 Kernel Pages 的过滤配置适合许多内核崩溃，但分析用户地址空间、Pinned Page、DMA Buffer 或混合对象时可能不够。
#. 过滤后的页面缺失会在 Crash 分析中表现为不可读地址、零填充、对象字段缺失或命令失败。
#. 分析者必须知道 Dump Level，不能把“页面未保存”误判为“崩溃时页面不存在”。
#. ``vmcore-dmesg`` 或相关工具可从 Vmcore 提取日志缓冲，但它不能替代结构体、栈和对象分析。
#. Pstore 是内核将崩溃、Oops、Console 或 Ftrace 等少量记录写入持久后端的框架。
#. Ramoops 是使用预留 RAM 作为 Pstore 后端的常见方案；重启后可在 ``/sys/fs/pstore`` 读取短日志。
#. Pstore/Ramoops 保存容量有限，适合最后几段文本，不是完整内存镜像。
#. Kdump 与 Pstore 互补：前者保存大范围内存对象，后者在 Capture 失败时仍可能留下最后日志。
#. Pstore 也依赖提前配置保留区、后端和文件系统挂载；文件存在与否要结合配置判断。
#. 普通 ``dmesg``、Journal、Serial Console、Netconsole 属于即时输出层，容易在严重崩溃中截断或丢失。
#. Crash-time 证据可分为：即时日志、持久短日志和 Vmcore 三层；每层容量、可靠性与分析深度不同。
#. Panic、Oops、WARN、Soft Lockup、Hard Lockup、Hung Task 与 RCU Stall 不完全等价。
#. 是否最终进入 Kdump 取决于 ``panic_on_oops``、``panic_on_warn``、Watchdog Panic、Sysrq Crash 和其它策略。
#. Oops 后继续运行可能保留更多在线证据，也可能让损坏扩散；生产策略应按可靠性和可用性目标决定是否 Panic。
#. ``sysrq-trigger`` 的 Crash 触发可用于验证 Kdump，但会立即使测试机崩溃，必须在隔离环境和正式变更窗口执行。
#. “服务显示 Active”或“Crash Kernel Loaded”不等于端到端测试成功。
#. Kdump 验收必须真正触发一次受控崩溃，并确认重启后得到可被 Crash 工具打开的 Vmcore。
#. 测试应验证本地/远端目标、文件大小、压缩、时间、Kernel Release、Vmlinux 匹配和日志提取。
#. 测试后要确认生产内核、Crash Kernel、Initramfs 和 Boot Entry 在升级中如何同步更新。
#. 内核升级后旧 Crash Kernel 可能仍被加载；应自动检查运行 Kernel 与 Loaded Capture Image 的 Generation。
#. Crash Kernel 不一定必须和生产内核完全相同，但必须能正确读取架构提供的旧内存视图并驱动收集路径；发行版通常提供推荐组合。
#. 后续 ``crash`` 分析使用的 ``vmlinux`` 必须匹配崩溃的第一内核，而不是 Dump-capture Kernel。
#. Vmcore 的 Kernel Release、Build ID、Config、KASLR 和 Module 信息必须与分析符号对应。
#. Pstore 中的日志属于第一内核；第二内核和收集服务也会产生自己的日志，时间线要分开。
#. 崩溃重启后应记录 Boot ID 变化，以免把 Capture Kernel、重启后的正常内核和故障前实例日志混在一起。
#. Capture Kernel 的 Initramfs 应只包含必要驱动、文件系统、网络和收集工具，避免复杂用户态依赖。
#. 动态存储路径、网络名称和设备枚举可能在第二内核中不同，不能依赖生产系统中的偶然顺序。
#. 使用 UUID、稳定网络配置、固定 BDF/设备身份和明确脚本可降低枚举差异。
#. IOMMU、Firmware、PCI Reset、Multipath、MD RAID、LVM、加密盘和网络 Bonding 会增加 Capture 路径复杂度。
#. 对复杂生产平台，应设计独立、简单的 Dump Target，而不是假设正常 Rootfs 全部可用。
#. Capture 环境若需要解密密钥或网络凭证，要控制其存储和暴露风险。
#. Vmcore 保存失败时，Capture Kernel 日志本身是重要证据，应持久保存到 Console、Pstore 或远端。
#. 收集脚本应返回明确状态，记录失败阶段，而不是只在目标目录没有文件时留下空白。
#. 磁盘空间不足应在日常运行中监控；等待崩溃后才发现空间不足已经无法恢复现场。
#. Retention 应按最大可能 Vmcore 大小、压缩率、故障频率和上传速度容量规划。
#. 自动删除策略必须避免在调查未完成前覆盖唯一现场。
#. 远程上传应校验大小、Hash、原子完成标记和重试，避免把截断文件当成成功 Vmcore。
#. 保存成功后应只读保护原始 Dump，分析时使用副本，防止工具或传输损坏原件。
#. Vmcore 和 Vmlinux 应建立不可歧义配对，例如按 Boot ID、Release、Build ID 和时间目录组织。
#. 同一 Kernel Release 字符串可能来自不同 Build，Release 相同不保证结构布局和符号完全匹配。
#. 自编译内核必须保存构建目录中的 ``vmlinux``、``System.map``、``.config``、Module 和 Build Metadata。
#. 发行版内核应安装对应 Debuginfo 包并验证 Build ID，而不是只下载相同版本号的任意包。
#. KASLR 信息通常随 Vmcore/VMCOREINFO 被记录，分析工具依赖正确元数据恢复符号地址。
#. ``VMCOREINFO`` 保存关键符号、结构偏移、Page Size 等信息，帮助工具解释崩溃内存。
#. VMCOREINFO 有助于跨构建解释，但不能替代匹配的完整 Vmlinux 和类型信息。
#. Kdump 不能提供崩溃前完整事件时间线；Vmcore 是一个冻结时刻，之前的因果仍需日志、Trace、Counter 和复现。
#. 内存破坏可能在很早之前发生，Panic 栈只表示最后发现坏状态的位置。
#. 即使 Vmcore 完整，损坏对象字段也可能已经不可信；分析要使用多个独立证据交叉验证。
#. Hard Lockup 中其它 CPU 的状态和 NMI 响应可能不完整，是否成功停止全部 CPU 取决于架构和故障类型。
#. Capture 路径自身也可能因硬件故障、总线卡死或 Firmware 失控而失败；不能只部署单一证据渠道。
#. Pstore、BMC/Serial、Watchdog、Remote Logging 与 Kdump 应形成分层冗余。
#. Kdump 配置属于高风险启动和内存变更，修改 ``crashkernel=`` 后必须重启才能改变预留布局。
#. 远程生产主机修改前应准备可回退 Boot Entry、Console/BMC 和内存容量评估。
#. 预留区变化可能影响 NUMA、Huge Page、CMA、IOMMU 和可用内存，升级后要重新做容量测试。
#. Kdump 安全边界包括 Kexec 加载权限、Crash Image 签名、Dump 读取权限和目标存储权限。
#. 能读取 Vmcore 等价于读取大量内核和用户内存，不应向普通运维账户开放。
#. ``/proc/vmcore`` 只在 Dump-capture Kernel 中代表旧内核镜像；普通生产内核中通常不存在同类可读内容。
#. 收集完成后第二内核应按明确策略重启、关机或停留，避免在不完整环境中误当生产系统运行。
#. 一份有效 Kdump 运行手册应记录：触发条件、预留大小、Capture Image、目标、过滤级别、超时、失败路径、验证频率和分析符号位置。
#. 故障复盘必须同时记录“为什么系统崩溃”和“为什么证据成功或失败被保存”。
#. 源码阅读顺序是：Panic/Crash Trigger → ``crash_kexec`` → Reserved Memory/Kexec Image → Dump-capture Kernel → ``/proc/vmcore`` → Makdumpfile/Transport → Artifact Validation。

必背路径
--------

Kdump 准备：

::

   Boot Entry 配置 crashkernel=
   → 第一内核启动并预留物理内存
   → Kdump 服务构建/选择 Capture Kernel 与 Initramfs
   → kexec -p 加载到保留区
   → 检查 Crash Kernel Reserved 与 Loaded 状态
   → 定期执行受控 Crash 验收

崩溃收集：

::

   Panic/Oops/Lockup 触发 Crash Policy
   → 停止或通知其它 CPU
   → crash_kexec 切入 Dump-capture Kernel
   → 第二内核初始化最小存储/网络路径
   → /proc/vmcore 暴露第一内核内存
   → makedumpfile 过滤/压缩
   → 写本地或远端目标
   → 校验大小、Hash、Release 和完成标记

Pstore 补充：

::

   崩溃前预留 Ramoops/Pstore 后端
   → Panic/Console/Ftrace 写入有限持久区域
   → 系统重启
   → 挂载 Pstore
   → 从 /sys/fs/pstore 读取最后短日志
   → 与 Vmcore、Journal 和 Boot ID 关联

端到端验收：

::

   确认可回退测试环境
   → 记录运行 Kernel 与 Loaded Crash Kernel
   → 受控触发 Sysrq Crash
   → Capture Kernel 启动并保存 Dump
   → 正常系统重启
   → 找到 Vmcore 与日志
   → 使用匹配 Vmlinux 启动 crash
   → 保存测试结果与失败阶段

必须区分
--------

Panic 触发与 Vmcore 成功
   进入崩溃路径不代表第二内核、存储和收集脚本全部成功。

Crash Kernel 与崩溃内核
   前者负责收集；后者是发生故障并被保存在 Vmcore 中的第一内核。

Vmcore 与 Vmlinux
   Vmcore 提供冻结内存；Vmlinux 提供符号、类型和结构布局。

Pstore 与 Kdump
   Pstore 保存少量持久文本；Kdump 保存完整或过滤后的内存镜像。

完整 Dump 与过滤 Dump
   完整 Dump 信息多、体积大；过滤 Dump 体积小但可能缺少目标页面。

配置存在与端到端可用
   服务、参数和 Loaded 状态只是准备证据；真正验收必须触发并打开一次 Dump。

Capture Kernel 日志与第一内核日志
   前者描述收集环境；后者描述崩溃现场，时间线和对象不同。

一句话结论
----------

Kdump 的本质是在系统仍健康时预先隔离一条最小崩溃收集路径，使 Panic 后不再依赖已经失去可信度的生产内核运行环境。

来源
----

* 书籍：Linux Kernel AIBook；
* Part：Part 35 — Kernel Debugging, printk, Dynamic Debug, ftrace, perf, kdump, and crash；
* 章节：Chapter 174 — kdump and vmcore Collection；
* 源文件：``docs/LinuxK/Part_35_Kernel_Debugging_printk_Dynamic_Debug_ftrace_perf_kdump_and_crash/Chapter_174_kdump_and_vmcore_Collection.md``；
* 固定提交：``18386764582829f2b807b7b0947785eb77b50446``；
* 固定来源：``https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_35_Kernel_Debugging_printk_Dynamic_Debug_ftrace_perf_kdump_and_crash/Chapter_174_kdump_and_vmcore_Collection.md``。
