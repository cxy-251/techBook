第167章：Module Parameters 与驱动专用调优
=========================================

本章必须记住
------------

#. Module Parameter 是驱动或子系统在加载、初始化、Probe 或运行路径中接收少量策略输入的正式机制。
#. 参数本身只完成“用户字符串 → 类型转换 → 内核变量或回调”的控制入口；硬件后果来自驱动怎样使用该值。
#. 读一个模块参数必须追踪四件事：声明位置、输入来源、读取时机、最终影响的硬件或软件状态。
#. ``module_param()`` 通常把变量、类型和 sysfs 权限登记到内核参数表。
#. ``MODULE_PARM_DESC()`` 提供参数说明，便于 ``modinfo -p`` 和文档工具展示。
#. ``module_param_named()`` 可让用户态参数名与内部变量名不同。
#. ``module_param_array()`` 暴露数组输入；必须同时检查元素数量、范围和实际消费逻辑。
#. ``module_param_cb()`` 使用自定义 ``kernel_param_ops``，解析或写入时可执行校验和副作用。
#. 参数类型决定字符串如何转成 ``bool``、``int``、``uint``、``ulong``、``charp`` 或其它状态。
#. 类型解析成功不表示值适合目标硬件；范围和设备能力仍应由驱动验证。
#. 驱动缺少范围检查时，一个小参数也可能造成 Probe 失败、Ring 越界、分配过大或寄存器非法配置。
#. 参数默认值属于驱动当前版本的设计选择，不是跨版本稳定硬件常量。
#. 参数声明处只证明入口存在，必须继续搜索变量全部引用或自定义 Set Callback。
#. 参数在 Probe 前读取，通常决定队列数量、Feature、Firmware、DMA、IRQ 或资源布局。
#. 参数在 Open/Start 路径读取，可能影响每次设备启用或接口启动。
#. 参数在热路径读取，运行时写入可能立即改变分支，但需要正确并发同步。
#. 参数只在初始化时读取，运行时修改变量不会自动重建已存在硬件状态。
#. 因此“sysfs 文件写入成功”与“设备已按新值重配置”必须严格区分。
#. 驱动若允许运行时重配置，Set Callback 应明确完成状态检查、停机、排空、重配和恢复。
#. 直接暴露普通变量为可写参数，却没有锁或重配置协议，容易形成软件值和硬件状态不一致。
#. 可加载模块参数可由 ``modprobe module parameter=value`` 或 ``insmod file.ko parameter=value`` 传入。
#. ``modprobe`` 会处理依赖、别名、黑名单和 ``modprobe.d`` 配置；``insmod`` 更接近直接提交指定 ``.ko``。
#. ``/etc/modprobe.d/*.conf`` 中的 ``options module key=value`` 只在相应模块通过 Kmod 路径加载时参与。
#. 修改 ``modprobe.d`` 不会追溯改变已经加载模块的当前参数。
#. 模块被依赖链提前自动加载时，之后手工 ``modprobe`` 传值可能已经太晚。
#. 需要改变 Load-time-only 参数时，通常必须先安全卸载模块或重启。
#. 模块不能卸载时，应先确认设备使用者、引用、内建状态和 Remove/Teardown 安全性。
#. 内建驱动没有独立的用户态插入事件，参数主要通过 Kernel Command Line 传入。
#. 内建参数常写成 ``module_name.parameter=value``，实际模块名应以构建和元数据为准。
#. 把内建驱动参数只写入 ``modprobe.d`` 不会影响早期初始化。
#. 同一源码在不同内核配置下可由 ``=y`` 变为 ``=m``，有效传参路径也随之改变。
#. 诊断第一步应通过配置、``modinfo``、``lsmod``、Sysfs 和启动日志确认驱动是 Built-in 还是 Loadable。
#. ``lsmod`` 未显示驱动不等于驱动不存在，它可能内建或由其它模块名承载。
#. ``modinfo -p`` 展示模块元数据中的参数名和描述，不能证明当前加载实例使用了哪个值。
#. ``/sys/module/<module>/parameters/<parameter>`` 展示当前内核变量的文本视图。
#. Sysfs 路径存在不表示驱动已成功绑定设备；模块对象与设备实例是不同层级。
#. 一个模块可控制多个设备，Module Parameter 通常是模块级全局策略，不是单设备属性。
#. 修改模块级参数可能影响同一驱动的所有后续设备或全部热路径调用。
#. 需要每设备独立控制时，更合适的接口可能是 Device Sysfs Attribute、Netlink、Devlink、EtHTool 或子系统正式 UAPI。
#. ``module_param`` 第三个参数是 Sysfs 文件权限，不是 C 变量内存保护。
#. 权限为 ``0`` 时通常不创建对应 Sysfs 参数文件。
#. ``0444`` 表示用户态可读，适合观察当前参数值。
#. ``0644`` 表示通常可由具备权限的用户写入，仍会经过 VFS、Kernfs、参数 Set Handler 和 LSM 检查。
#. 文件模式可写不等于任意用户可写，Mount、Credential、User Namespace、LSM 和 Lockdown 仍可能限制。
#. 只读参数通常表达 Load-time policy 或不支持在线重配的状态。
#. 可写参数必须定义新值从何时生效、影响已有对象还是未来对象、失败时如何回滚。
#. 参数输出是文本 ABI；布尔值、数组和字符串的格式应按 Parameter Ops 定义解释。
#. ``charp`` 一类字符串参数涉及指针和内存生命周期，不能假设写入只是覆盖固定缓冲区。
#. 自定义 Callback 可拒绝非法值并返回 ``EINVAL``、``ERANGE``、``EBUSY`` 等错误。
#. 用户态看到写入字节数成功，只说明 Callback 接受输入；设备内部异步重配置仍可能稍后失败。
#. 若重配置可能异步失败，驱动应提供状态、日志或事件接口，而不是只更新参数文件。
#. 参数改变队列数量时，要考虑硬件最大队列、CPU 数、MSI-X 向量、DMA 内存和上层框架限制。
#. 请求 64 条队列并不表示硬件和驱动最终创建 64 条；可能被裁剪、共享或 Probe 失败。
#. 参数改变 Ring Size 时，要考虑 Descriptor 数、Memory Footprint、Doorbell、Completion 和 BQL/NAPI 等关联状态。
#. 参数改变 IRQ 模式时，要考虑 MSI-X/MSI/INTx 回退与亲和性。
#. 参数改变 DMA、IOMMU 或缓存策略时，错误值可能导致数据破坏，不只是性能变化。
#. 参数改变 Firmware、Power、Clock 或 Reset 行为时，可能影响 Probe、Suspend/Resume 和 Reset Recovery。
#. 参数改变 Debug 输出时，过量日志会改变时序、占用 Ring Buffer 并放大锁竞争。
#. Debug Parameter 应支持 Rate Limit 或精确范围，不能在高频 IRQ/NAPI/I/O 路径无条件打印。
#. 参数禁用硬件 Feature 可用于二分故障，但长期禁用可能损失性能、可靠性或安全能力。
#. Offload、Queue、Power Saving 等参数的收益取决于设备型号、Firmware 和工作负载。
#. 不存在跨设备通用的“最佳模块参数”。
#. 读驱动参数时应先读官方参数文档、Kconfig Help、``MODULE_PARM_DESC`` 和目标版本源码。
#. 发行版可能通过 Patch 改默认值、隐藏参数或加入安全限制。
#. 模块参数属于 Kernel UAPI 的稳定程度因参数而异；驱动私有参数可能跨版本变化或删除。
#. 自动化必须容忍参数不存在，并按 Kernel/Driver Version 选择配置。
#. 依赖未文档化参数会把生产系统绑定到内部实现。
#. 参数持久化应写入正式 Bootloader 或 Kmod 配置源，而不是只在当前 Shell 执行一次命令。
#. 对内建驱动，持久化通常进入 Kernel Command Line 管理。
#. 对可加载模块，持久化通常进入 ``modprobe.d``，并确认 Initramfs 是否包含该配置。
#. 早期由 Initramfs 加载的模块可能使用 Initramfs 内旧配置，更新 Rootfs 配置后需重建 Initramfs。
#. 模块别名加载时，``options`` 应针对真实模块名，不是设备 Modal Alias 字符串。
#. 参数名称错误时，模块加载可能直接失败，也可能输出 Unknown Parameter 警告。
#. 未知参数是否被拒绝取决于加载路径和参数表，不应依赖静默忽略。
#. 模块参数可包含敏感信息时，Sysfs 权限和日志输出必须避免泄漏。
#. 密钥、令牌和长期 Secret 不适合通过明文 Module Parameter 传递。
#. 参数写入属于控制面，生产环境应限制 ``CAP_SYS_MODULE``、Sysfs 写权限和容器设备访问。
#. User Namespace 中的 Root 通常不能任意修改宿主模块参数，实际权限受 Initial User Namespace 和 LSM 控制。
#. Secure Boot/Lockdown 可能限制模块加载、调试和部分硬件参数。
#. 模块签名验证发生在参数影响驱动前；签名成功不证明参数安全。
#. 运行时写参数前必须记录原值、目标值、设备状态、负载和回滚步骤。
#. 一次只修改一个参数，否则无法把结果归因到具体变量。
#. 修改后应观察驱动日志、设备 Sysfs、队列、IRQ、错误计数、吞吐和尾延迟。
#. 只看参数文件新值不足以验证硬件状态。
#. 写入失败后要确认变量是否保持原值、是否部分产生副作用、设备是否需要 Reset。
#. 一个合格 Set Callback 应先验证所有前提，再发布新状态，避免失败后留下半配置。
#. 在线重配置应阻止新工作、排空在途请求、同步 IRQ/Worker、修改硬件，再恢复入口。
#. Teardown 与参数写入可能并发，回调必须取得对象引用并检查 Module/Device 正在退出。
#. Module Parameter 属于模块对象，模块卸载前必须阻止新的 Sysfs 写入并等待进行中的 Callback。
#. ``module_param_cb`` 的 Set Handler 上下文可以睡眠与否应按具体参数框架和调用路径确认。
#. Callback 不应在持有不合适全局锁时执行长时间硬件操作。
#. 复杂运行时配置应优先使用支持事务、ExtAck、事件和对象作用域的专用控制接口。
#. 参数实验导致 Probe 失败时，应比较默认值与新值下的资源申请、硬件能力和错误路径。
#. 参数实验导致性能下降时，应区分 CPU、内存、IRQ、Queue、DMA、Firmware 和应用负载变化。
#. 参数实验导致第二次 Reload/Resume 失败时，重点检查初始化值是否被重复消费或资源未恢复。
#. 参数值可能只在首次 Probe 缓存到设备私有结构，之后修改模块全局变量不会改变该缓存。
#. 多设备系统中，新热插设备可能使用新值，旧设备继续使用旧值，形成混合状态。
#. 诊断必须记录每个设备的创建时间和实际配置，不只看模块全局参数。
#. 驱动若公开实际队列数、Feature 或模式，应以实际状态接口为准。
#. 不应通过无限增大 Queue/Ring/Timeout 掩盖硬件卡死、锁竞争或 Completion 丢失。
#. Timeout 参数变大可能只延迟错误暴露，并扩大在途资源占用。
#. Retry 参数变大可能造成请求风暴和尾延迟恶化。
#. 禁用安全校验、IOMMU 或错误恢复的参数不能当作普通性能优化。
#. 修复应优先消除根因，参数只用于选择受支持策略或受控回退。
#. 精确宏、参数权限语义、Kmod 配置和 Sysfs 实现具有版本差异。
#. 稳定源码阅读顺序是：Parameter Declaration → Input Source → Parse/Callback → Variable References → Device State → Runtime Evidence → Teardown。

必背路径
--------

可加载模块参数：

::

   modprobe/insmod/modprobe.d 提供字符串
   → 模块加载器取得参数
   → Kernel Parameter Framework 查找 module_param 元数据
   → 类型转换或自定义 Set Callback
   → 写入模块变量
   → Module Init / Bus Probe / Open 路径读取
   → 改变驱动资源和硬件策略

内建驱动参数：

::

   Bootloader Command Line
   → module_name.parameter=value
   → 启动期通用参数解析
   → 内建驱动 Initcall / Probe 读取变量
   → 创建设备实例与硬件状态

运行时写入：

::

   写 /sys/module/<module>/parameters/<name>
   → Kernfs/Sysfs 权限检查
   → Parameter Set Handler
   → 解析和验证新值
   → 若支持在线重配则排空并修改硬件
   → 更新状态并返回
   → 通过实际设备接口验证结果

参数排障：

::

   确认 Built-in 或 Loadable
   → modinfo -p / 查看源码声明
   → 读取当前 Sysfs 参数值
   → 查找变量全部引用
   → 确认首次读取和缓存时机
   → 对照设备实际队列、Feature、IRQ 和日志
   → 找到参数值与硬件状态的第一个差异

必须区分
--------

* 参数变量已更新与硬件已重配置：Sysfs 写入可以只改变软件变量；已有设备状态需要驱动显式执行重配置。
* 模块级参数与设备级属性：Module Parameter 通常影响整个驱动；Device Attribute 绑定具体设备实例。
* Built-in 与 Loadable：内建驱动从 Kernel Command Line 获得参数；可加载模块可由 Kmod/Insmod 传入。
* Load-time Policy 与 Runtime Control：只在 Init/Probe 消费的参数需要 Reload/重启；运行时控制必须有并发和回滚协议。
* 参数当前值与最终有效值：驱动可能按硬件能力裁剪、缓存或转换，实际状态应从设备接口和日志验证。

一句话结论
----------

Module Parameter 是驱动的策略输入口，不是硬件状态本身：只有追踪参数被何时读取、怎样验证和如何重配置，才能证明它真正生效。
