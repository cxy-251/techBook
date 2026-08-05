第116章：Linux 设备模型作为内核对象层级
=======================================

本章必须记住
------------

#. Linux 设备模型把 PCI、USB、I2C、SPI、platform、固件描述设备和虚拟设备纳入同一套对象、匹配、属性、事件与生命周期基础设施。
#. 不同总线仍负责各自的枚举、地址、ID、资源和协议；driver core 只统一它们进入内核后的公共对象关系。
#. ``struct device`` 是 driver core 中一个设备实例的通用身份，实际总线对象通常把它嵌入更大的 bus-specific 结构体。
#. ``struct device`` 不代替 ``struct pci_dev``、``struct usb_interface``、``struct platform_device`` 等专用对象；它提供公共设备模型层。
#. 看到通用 ``struct device *`` 时，应使用总线或子系统提供的转换 helper 回到宿主对象，不能盲目强制转换。
#. ``struct device_driver`` 表示能处理一类设备的软件实现；一个驱动对象可以绑定多个设备实例。
#. ``struct bus_type`` 表示设备和驱动相遇的匹配域，保存设备集合、驱动集合及匹配、probe、remove、uevent、PM 等公共回调。
#. ``struct class`` 按用户空间功能组织设备，例如 net、block、input、tty；它不表示设备的物理连接总线。
#. Device 回答“这个实例是谁”，driver 回答“谁控制它”，bus 回答“怎样匹配”，class 回答“用户空间按什么功能看它”。
#. ``dev->parent`` 建立设备父子层级，通常表达硬件拓扑、逻辑包含、接口关系或生命周期依赖。
#. 父子层级决定 `/sys/devices` 中的主要目录结构，也影响移除、电源管理和子设备注销顺序。
#. Class 视图和 bus 视图通常通过符号链接指向 `/sys/devices` 中的同一 canonical device 对象。
#. `/sys/class/net/eth0`、`/sys/bus/pci/devices/...` 和 `/sys/devices/...` 可以是同一设备关系的不同入口。
#. 设备模型层级不一定等同于纯物理电路图；虚拟设备、接口对象、逻辑子设备也会进入该树。
#. ``dev->bus`` 指向设备所属匹配域；``dev->driver`` 只在成功绑定后指向当前驱动。
#. ``dev->class`` 表达功能视图，设备可以没有 class，也可以由上层子系统创建另一个 class device 表达用户接口。
#. 一个硬件设备可以产生多个功能对象，例如一个 USB 复合设备拥有多个 interface，每个 interface 可独立绑定驱动。
#. 一个 PCI 网卡的 PCI device 与注册出的 ``net_device`` 是不同对象，前者表达硬件实例，后者表达网络功能接口。
#. ``struct device`` 内嵌 ``struct kobject``，名称、sysfs 层级和基础引用计数由 kobject 基础设施支撑。
#. 设备对象不能直接在任意时刻 ``kfree()``；注册后必须经 device/kobject 引用协议进入最终 release 回调。
#. 每个动态设备对象必须有明确 release 路径，最后引用归零时才能释放宿主内存。
#. ``device_initialize()`` 只初始化对象；``device_add()`` 才把它加入设备模型并建立可见关系。
#. ``device_register()`` 通常组合初始化和添加；失败后的清理必须遵守接口规定，不能重复初始化或直接释放。
#. 成功 ``device_add()`` 后，sysfs、bus、parent、class、uevent 和匹配路径可能已经持有或观察该对象。
#. 设备删除通常使用 ``device_del()`` 撤销可见性，再用 ``put_device()`` 释放创建者引用。
#. ``device_del()`` 不等于对象内存立即释放；其它引用仍可延长设备对象寿命。
#. 对象内存存活不等于硬件仍可访问；设备移除后，旧引用只能安全观察退出状态，不能继续无条件访问寄存器或提交 DMA。
#. Bus framework 发现设备后，通常先建立 bus-specific 对象和资源描述，再设置 parent、bus、release 等公共字段并加入 driver core。
#. 驱动注册后，driver core 会把它与同一 bus 中未绑定的设备尝试匹配；设备新增时也会反向扫描已有驱动。
#. 匹配成功只说明设备和驱动身份兼容；只有 probe 成功返回后，绑定和设备功能初始化才成立。
#. Probe 负责设备实例级资源与功能建立；driver core 不知道驱动内部申请了哪些 IRQ、DMA、clock、queue 或上层接口。
#. Probe 失败必须撤销已经完成的私有初始化，driver core 只能处理公共绑定状态。
#. ``-EPROBE_DEFER`` 表示依赖尚未准备好，需要稍后重试，不等同于永久不匹配或硬件失败。
#. Deferred probe 应在暴露用户接口或创建复杂子设备前尽早返回，降低回滚和重复注册风险。
#. 成功绑定后，driver core 会建立 device-driver 关系和相应 sysfs 链接；具体时序以目标内核实现为准。
#. Uevent 是内核向用户空间报告对象 add、remove、change、bind、unbind 等状态变化的机制之一。
#. Uevent 通常携带 ACTION、DEVPATH、SUBSYSTEM、MODALIAS 等环境信息，具体字段由 kset、bus、class 和设备回调补充。
#. Uevent 是事件通知，不是完整设备状态快照；用户空间收到事件后应重新读取 sysfs 或设备节点状态。
#. Add uevent 发出前，对象应已经具备用户空间随后访问所需的核心属性和关系。
#. Remove uevent 表示对象正在撤销可见性，不保证所有旧 fd、引用和异步请求已经自然消失。
#. Udev 等用户空间组件可依据 uevent 创建设备节点、符号链接、权限和命名策略；``/dev`` 节点不是设备对象本体。
#. 删除 `/dev` 节点不能注销内核设备；内核设备消失也可能因旧打开 fd 而继续保留部分对象状态。
#. ``modalias`` 用于把设备身份转换为模块匹配字符串，用户空间可据此加载候选驱动模块。
#. 模块加载只让驱动进入匹配域，不保证 probe 成功；仍可能因资源、依赖或硬件状态失败。
#. Device links 可以表达 supplier/consumer 依赖，帮助 driver core 安排 probe、runtime PM、suspend/resume 和 teardown 顺序。
#. Device link 不替代驱动内部资源引用和并发同步，它只表达设备对象之间的依赖关系。
#. 电源管理路径可能由 driver、bus、class、PM domain 多层包装，读源码时必须确认真正被调用的回调层级。
#. Parent-child 与 supplier-consumer 是不同关系；一个设备的资源供应者不一定是它的 parent。
#. Class 设备通常用于用户功能入口，物理拓扑应回到其 ``device``、``parent`` 或 sysfs 链接继续追踪。
#. Bus 目录中的 driver、bind、unbind 等控制面可能允许手工改变绑定，操作会触发生命周期收束，不能视为普通文件修改。
#. 手工 unbind 前必须评估文件系统、网络接口、打开句柄、DMA 和业务依赖，否则会造成 I/O 中断或数据丢失。
#. Driver override 可以改变候选匹配策略，具体接口和安全边界属于总线与版本敏感实现。
#. 设备模型的公共锁和引用只保护对象关系，驱动私有数据仍需自己的锁、状态机、引用或 RCU 协议。
#. Sysfs 目录仍存在不表示 probe 一定成功；应检查 ``driver`` 链接、uevent、日志和功能接口。
#. 没有 ``driver`` 链接可能表示没有候选驱动、匹配失败、probe 失败、defer、手工 unbind 或设备正在移除。
#. 同一个设备名在不同 bus 或 namespace 语境中未必唯一，诊断时应记录完整 DEVPATH、major/minor、PCI BDF、USB path 等稳定身份。
#. 容器中的 `/sys` 可能被过滤或只读，看到的设备视图不一定等同于宿主机完整设备模型。
#. 虚拟机中的 parent、NUMA、PCI 和热插拔关系可能由 hypervisor 合成，不能直接推断宿主物理拓扑。
#. 设备模型分析应按对象关系而非目录字符串猜测：device → parent → bus → driver → class → module → uevent。
#. 稳定模型是“硬件或逻辑实例进入统一对象层级”；精确字段、注册 helper 和事件时机属于版本敏感实现。

必背路径
--------

设备注册：

::

   Bus/firmware framework 发现设备
   → 创建 bus-specific container
   → 初始化内嵌 struct device
   → 设置 name、parent、bus、release 和资源关系
   → device_add / bus-specific register
   → 加入设备层级与 bus 集合
   → 建立 sysfs 表示
   → 发送 add uevent
   → 尝试匹配已有 driver

驱动注册与绑定：

::

   驱动模块初始化
   → 注册 bus-specific driver
   → 内嵌 struct device_driver 进入 bus driver 集合
   → 扫描同一 bus 的未绑定设备
   → bus match
   → 调用 probe
   → 申请设备实例资源并注册功能接口
   → probe 返回 0
   → 建立成功绑定关系

设备删除：

::

   标记设备正在移除
   → 阻止新功能请求
   → 解绑 driver 并执行 remove
   → 注销 class/子系统接口
   → 删除 sysfs 与 bus/class 可见关系
   → 发送 remove uevent
   → device_del
   → 释放创建者引用
   → 最后引用归零后 release 宿主对象

从 sysfs 还原对象：

::

   从 /sys/class 或 /sys/bus 入口开始
   → readlink -f 回到 /sys/devices canonical path
   → 沿 parent 目录确认拓扑
   → 检查 subsystem 链接确定 bus/class
   → 检查 driver 链接确定绑定
   → 检查 module 链接确定代码来源
   → 结合 uevent 和 dmesg 确认状态变化

检查设备模型关系：

::

   确认 struct device 宿主类型
   → 确认谁初始化和注册
   → 确认 parent 与 supplier
   → 确认 bus match 规则
   → 确认 probe 建立哪些功能对象
   → 确认 class 用户视图
   → 确认 remove 与 release 最终责任

必须区分
--------

``struct device`` 与总线专用设备对象
   Device 是公共身份；PCI、USB、platform 等宿主对象保存总线专用状态。

Bus 与 Class
   Bus 负责设备—驱动匹配；class 按用户空间功能组织已经存在的设备。

Match 成功与 Probe 成功
   Match 只确认候选兼容；probe 成功才表示驱动完成实例初始化和绑定。

``device_del`` 与对象释放
   Del 撤销设备模型可见性；内存要等所有引用归零并进入 release 回调。

对象内存存活与硬件可用
   引用可以保留软件对象；设备移除后硬件访问必须由退出状态禁止。

Uevent 与设备状态
   Uevent 是变化通知；完整状态需要重新查询 sysfs、驱动和子系统对象。

一句话结论
----------

Linux 设备模型用 ``struct device`` 把不同总线实例接入统一父子层级，再由 bus 匹配 driver、class 提供功能视图，并用 kobject 引用与 uevent 管理可见性和最终释放。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 24，Device Model, Kobject, Sysfs, Driver Core, and Device Lifetime；
* AIBook 章节：Chapter 116，Linux Device Model as a Kernel Object Hierarchy；
* 源文件：``docs/LinuxK/Part_24_Device_Model_Kobject_Sysfs_Driver_Core_and_Device_Lifetime/Chapter_116_Linux_Device_Model_as_a_Kernel_Object_Hierarchy.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_24_Device_Model_Kobject_Sysfs_Driver_Core_and_Device_Lifetime/Chapter_116_Linux_Device_Model_as_a_Kernel_Object_Hierarchy.md>`_。