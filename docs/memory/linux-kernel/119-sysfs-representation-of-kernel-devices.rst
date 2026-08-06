第119章：Sysfs 中的内核设备表示
===============================

本章必须记住
------------

#. Sysfs 是内核对象、属性和对象关系的用户空间投影，不是磁盘配置文件树。
#. 同一设备可同时出现在 ``/sys/devices``、``/sys/bus``、``/sys/class``、``/sys/module`` 等视图中。
#. 这些路径通常不是多个独立设备对象，而是 canonical object 加符号链接形成的交叉视图。
#. ``/sys/devices`` 是设备父子层级的主视图，最适合观察真实或逻辑拓扑。
#. ``/sys/bus/<bus>/devices`` 按匹配域列出设备，条目通常链接回 ``/sys/devices``。
#. ``/sys/bus/<bus>/drivers`` 按驱动列出当前绑定设备和部分绑定控制接口。
#. ``/sys/class/<class>`` 按用户空间功能组织设备，例如 net、block、input、tty。
#. 从 class 或 bus 路径分析设备时，应使用 ``readlink -f`` 回到 ``/sys/devices`` 中的 canonical path。
#. Canonical path 的父目录链表达设备模型 parent 关系，不一定等同于纯物理电路结构。
#. 虚拟设备、接口对象、分区、逻辑子设备和固件节点也会出现在 ``/sys/devices`` 层级中。
#. ``subsystem`` 链接通常指向所属 bus 或 class 目录，用于识别当前对象的子系统语境。
#. ``driver`` 链接表示当前 device-driver 绑定；没有该链接不等于设备对象不存在。
#. ``driver/module`` 链接可进一步关联到提供驱动代码的模块；内建驱动可能没有可卸载模块对象。
#. Class device 的 ``device`` 链接常用于回到它依赖的物理或总线设备，但不同子系统的关系形态不完全相同。
#. ``uevent`` 文件可以输出对象事件环境信息，也可能接受受支持的事件触发写入；具体行为依对象与版本而定。
#. Sysfs 路径和文件名一旦被用户空间依赖，可能形成长期 ABI；不能把内部调试数据随意放入稳定属性。
#. Sysfs 属性通常使用 ASCII 文本，一个文件表达一个逻辑属性。
#. “一个值”不是必须只有一个数字；同类型数组可以合理存在，但复杂混合格式应避免。
#. ``struct attribute`` 保存名称和权限，``struct device_attribute`` 把属性与 device 的 show/store 回调连接起来。
#. 读取属性进入 ``show()``，写入属性进入 ``store()``；回调面对的是当前对象状态，不是缓存好的静态文件内容。
#. Show 回调应使用 ``sysfs_emit()`` 一类 helper 格式化输出，并遵守页大小和返回值约束。
#. Store 回调必须严格解析输入、验证范围和状态，成功时通常返回已消费字节数，失败时返回负 errno。
#. Sysfs 写入不是事务接口；复杂多字段状态变化不应依赖多次属性写天然原子。
#. 属性权限是接口边界之一，不能用 world-writable 属性暴露危险硬件控制而缺少能力和状态检查。
#. 属性回调可以睡眠时必须使用允许睡眠的锁；不能持 spinlock 执行可能阻塞的 sysfs 操作。
#. Sysfs 核心可保护对象内存的基础生命周期，但驱动仍要检查设备是否 online、removed、suspended 或 error。
#. 对象引用仍存活不表示硬件可访问，属性回调必须拒绝对已移除设备进行寄存器、DMA 或固件操作。
#. Attribute group 把一组属性统一挂到对象或对象类型上，便于注册和撤销。
#. 默认 groups 可以在 device、driver、class 或 ktype 注册阶段自动创建，具体入口依高层对象 API。
#. 动态添加属性后失败时必须撤销已创建文件；属性组 helper 可以降低部分中间状态复杂度。
#. Bin attribute 用于需要二进制或较大数据接口的特殊场景，不应为逃避清晰 ABI 设计而滥用。
#. Sysfs 不是高带宽数据通道，不适合频繁大块数据传输、日志流或复杂命令协议。
#. 高带宽或事件流应使用 char device、netlink、tracefs、relay、ioctl 或子系统专用接口。
#. ``/sys/module/<module>`` 展示模块参数、sections、holders 等模块视图，不等同于设备绑定状态。
#. 一个模块可服务多个驱动或设备；设备也可能由内建代码处理而没有对应可卸载模块。
#. Driver 目录中的设备链接表示当前绑定实例，``bind``/``unbind`` 接口是否可用取决于 bus 和配置。
#. 手工写 bind/unbind 会执行真实生命周期操作，可能中断网络、存储或其它业务，不能当成只读诊断。
#. ``new_id``、``remove_id``、``driver_override`` 等接口改变匹配策略，具体语义和风险属于总线敏感实现。
#. ``/sys/dev/char/<major>:<minor>`` 与 ``/sys/dev/block/<major>:<minor>`` 可把 dev_t 映射回对应 class/device 对象。
#. Major/minor 只表示字符或块设备号，不等同于 PCI BDF、USB path 或其它总线身份。
#. ``/sys/block`` 是块设备的兼容/功能视图；分区、holders、slaves 和 queue 目录可继续建立块设备层级。
#. ``slaves``/``holders`` 表示块设备依赖关系，不是通用 device parent 关系的替代品。
#. 网络接口名称可以变化，追踪物理设备时应从 ``/sys/class/net/<if>/device`` 返回总线设备。
#. 虚拟网络接口可能没有物理 ``device`` 链接，此时应结合 ``iflink``、namespace 和网络子系统状态判断。
#. 容器内 sysfs 可能被过滤、只读或只挂载部分层级，不能据此断言宿主机没有某个对象。
#. Namespace 会影响网络、设备节点和挂载可见性，但 sysfs 设备模型本身并非所有对象都完整 namespace 化。
#. Sysfs 中目录消失表示对象可见性已撤销，不证明所有打开 fd、引用和异步 callback 已结束。
#. Sysfs 中目录仍存在也不证明 probe 成功或硬件健康，应检查 driver、state、error 和功能子系统。
#. Attribute read 成功只说明回调返回了当前软件状态，不自动证明硬件测量真实、未缓存或刚刚更新。
#. 属性可能由驱动缓存、固件、异步采样或设备寄存器提供，语义必须查对应 ABI 文档。
#. 稳定 sysfs ABI 应记录在 ``Documentation/ABI``，用户空间不应依赖未文档化 debug 属性和目录布局细节。
#. ``testing``、``stable``、``obsolete`` 等 ABI 分类表达维护状态，具体路径和文档格式以目标内核为准。
#. Debugfs 与 sysfs 必须区分：sysfs 面向对象属性和稳定接口，debugfs 通常不承诺稳定 ABI。
#. Procfs 与 sysfs 也不同：procfs 主要提供进程和系统运行视图，sysfs 主要投影对象模型和设备属性。
#. Uevent 是状态变化通知，sysfs 是随后读取对象状态的主要入口之一；二者应组合使用。
#. 用户空间收到 add 事件后可能立即读取属性，驱动必须在发事件前完成必要初始化。
#. 用户空间收到 remove 事件时对象可能已不可操作，处理程序应容忍链接和属性已消失。
#. 符号链接可能在解析过程中因热插拔变化，诊断脚本必须处理 ``ENOENT`` 和竞态。
#. 不能通过遍历 sysfs 无锁构造永久一致设备快照，热插拔系统需要重试或结合 udev monitor/sequence。
#. 读取 ``power`` 目录可以观察 runtime PM 等状态，但字段集合和语义依设备与内核配置。
#. ``authorized``、``remove``、``rescan``、``reset`` 等控制属性具有总线和设备特定危险性，不应未经确认写入。
#. 写 sysfs 属性前必须明确它是否会重置硬件、删除设备、改变电源或破坏数据路径。
#. ``lspci``、``lsusb``、``udevadm info``、``readlink`` 等工具本质上从不同接口组合设备模型信息。
#. ``udevadm info -q path`` 可提供 udev 看到的 DEVPATH，仍需回到 sysfs 链接验证实际对象关系。
#. ``udevadm monitor`` 观察事件顺序，不能替代 driver core 日志和 probe 返回码。
#. 诊断设备应记录 canonical path、bus identity、driver、module、class、dev_t、uevent 和 parent 链。
#. 只记录 ``eth0``、``sda`` 等易变化名称不足以关联热插拔前后的同一设备实例。
#. 设备重插后名称相同也可能是新对象，需使用序列号、BDF、port path、WWN 或其它总线稳定身份验证。
#. 稳定读取顺序是：class/bus 入口 → canonical device → parent → subsystem → driver/module → attributes → uevent。
#. 稳定模型是“sysfs 投影内核对象关系”；精确目录、属性、链接和权限属于子系统与版本敏感 ABI。

必背路径
--------

从 class 视图定位设备：

::

   /sys/class/<class>/<name>
   → readlink -f 解析 canonical path
   → 回到 /sys/devices/...
   → 沿 parent 目录确认拓扑
   → 读取 subsystem 链接确认 bus/class
   → 读取 driver 链接确认绑定
   → 读取 driver/module 确认代码来源

读取设备属性：

::

   用户 read 属性文件
   → sysfs 找到 attribute
   → 转入 device/kobject show 回调
   → 回调取得宿主对象
   → 检查对象和硬件状态
   → 在适当锁下读取状态
   → sysfs_emit 格式化 ASCII
   → 返回用户空间

写入设备属性：

::

   用户 write 属性
   → 权限和 LSM 检查
   → store 回调取得输入
   → 严格解析并检查范围
   → 检查 device online 与并发状态
   → 执行受控状态变化
   → 返回 count 或负 errno
   → 必要时发送 change uevent

检查 driver 绑定：

::

   定位 /sys/devices canonical device
   → 查看 driver 链接
   → 查看 /sys/bus/<bus>/drivers/<driver>
   → 确认反向设备链接
   → 查看 module 链接
   → 对照 modalias、dmesg 和 probe 结果

处理热插拔竞态：

::

   读取路径或链接失败
   → 判断对象是否正在 add/remove
   → 重新解析 canonical path
   → 对照 uevent sequence
   → 重新读取 driver 和属性
   → 不缓存永久 sysfs 文件描述符假设
   → 以最终对象身份验证结果

必须区分
--------

* ``/sys/devices`` 与 ``/sys/class``：前者展示设备父子层级；后者按用户功能提供交叉入口。
* ``/sys/bus`` 与 Driver 目录：Bus 视图组织匹配域；driver 目录展示当前驱动及其绑定设备。
* Sysfs 属性与普通文件：属性内容由内核回调即时生成或处理，不是磁盘上的持久文件数据。
* 对象内存有效与设备可操作：Sysfs 访问可保护软件对象；属性回调仍要检查硬件是否在线和允许操作。
* Uevent 与 Sysfs 状态：Uevent 通知发生了变化；sysfs 提供变化后对象关系和属性的可查询视图。
* Sysfs 与 Debugfs：Sysfs 面向对象属性和 ABI；debugfs 面向开发调试，通常不保证稳定接口。

一句话结论
----------

Sysfs 不是设备数据库，而是 ``kobject`` 和 driver core 对象关系的实时投影；正确读法是从 class/bus 链接回到 canonical device，再沿 parent、driver、module 和属性还原真实状态。
