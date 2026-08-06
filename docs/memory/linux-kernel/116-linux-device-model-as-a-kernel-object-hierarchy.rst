第116章：Linux 设备模型作为内核对象层级
=======================================

核心知识点
----------

设备模型统一公共关系
   PCI、USB、I2C、SPI、platform 与虚拟设备保留各自的枚举和协议规则，但都通过 driver core 进入统一的对象、匹配、属性、事件与生命周期框架。

``struct device`` 表示设备实例
   它保存父对象、总线、驱动、class、固件节点、电源状态和内嵌 ``kobject``。总线专用对象通常把 ``struct device`` 嵌入更大的结构体中。

``struct device_driver`` 表示控制实现
   一个驱动对象可绑定多个设备实例。共享的是代码和匹配表，每个实例的寄存器、IRQ、DMA 队列和运行状态必须独立。

``struct bus_type`` 定义匹配域
   Bus 组织同类 device 与 driver，并提供 match、probe、remove、uevent 和电源管理包装。具体身份规则由对应总线决定。

``struct class`` 提供功能视图
   Class 按 block、net、input、tty 等用户语义组织对象，不负责硬件发现，也不等于物理连接总线。

父子关系表达对象层级
   ``dev->parent`` 通常描述硬件拓扑、逻辑包含或生命周期层级，并形成 ``/sys/devices`` 的主要树形结构。

设备依赖不只靠 parent
   Supplier-consumer 关系可由 device link 表达，用于协调 probe、runtime PM、suspend/resume 和 teardown。它与父子关系不是同一概念。

注册分为初始化与发布
   ``device_initialize()`` 建立基础对象和初始引用；``device_add()`` 才把对象加入 driver core、sysfs、bus/class 关系和匹配流程。

发布后对象已可并发观察
   ``device_add()`` 成功后，用户空间、驱动匹配、sysfs 属性和 uevent 消费者都可能访问对象，后续状态必须满足并发和生命周期约束。

Match 与 probe 是两个阶段
   Match 只确认设备身份与驱动候选兼容；probe 成功后，驱动才建立实例资源、硬件状态和上层功能接口。

Deferred probe 表示依赖未就绪
   ``-EPROBE_DEFER`` 不是永久不匹配。它表示 clock、regulator、reset、PHY 或其它 supplier 尚未准备好，driver core 将在条件变化后重试。

Uevent 是变化通知
   Add、remove、bind、unbind 和 change 事件向用户空间报告对象变化。事件不是完整状态快照，接收者仍需重新读取 sysfs 和子系统状态。

设备节点不是设备对象
   Devtmpfs 或 udev 可依据 dev_t、class 和 uevent 创建 ``/dev`` 节点。删除节点不会注销内核对象，设备消失也不保证旧 fd 立即结束。

可见性撤销与内存释放分离
   ``device_del()`` 撤销 driver core 与 sysfs 可见关系；``put_device()`` 释放引用。只有最后引用归零后才进入 release 回调。

对象存活不等于硬件在线
   热拔插后，旧引用可以继续保护软件对象内存，但所有访问路径必须通过 dying、removed 或 disconnected 状态禁止继续访问失效硬件。

高层 API 维护完整关系
   Device、driver、bus 和 class 都包装了 kobject、列表、链接、模块和 PM 状态。不能用裸 kobject 操作替代对应的注册、解绑和引用接口。

关键路径
--------

设备注册：

::

   总线或固件框架发现设备
   → 创建总线专用宿主对象
   → 初始化内嵌 struct device
   → 设置 name / parent / bus / release
   → device_add
   → 建立 /sys/devices 与 bus/class 关系
   → 发送 add uevent
   → 尝试匹配已有驱动

驱动绑定：

::

   driver 注册到 bus
   → driver core 枚举未绑定 device
   → bus->match 检查身份
   → 调用 probe
   → 申请实例资源并初始化硬件
   → 注册 class 或子系统接口
   → probe 返回 0
   → 建立 device-driver 绑定

设备移除：

::

   标记设备退出
   → 阻止新请求
   → 解绑驱动并执行 remove
   → 撤销 class/子系统入口
   → device_del 删除可见关系
   → 发送 remove uevent
   → put_device 释放创建者引用
   → 最后引用归零
   → release 释放宿主对象

概念辨析
--------

* Device 与总线专用对象：Device 提供公共身份和生命周期；PCI、USB 等宿主对象保存协议专用状态。
* Bus 与 Class：Bus 负责设备—驱动匹配；class 按用户功能提供交叉视图。
* Parent 与 Device Link：Parent 表达对象层级；device link 表达 supplier-consumer 依赖。
* Match 与 Probe：Match 选择候选；probe 建立真正可用的设备实例。
* ``device_del`` 与 Release：Del 撤销可见性；release 在最后引用归零后释放内存。
* 对象存活与硬件可用：引用保护内存，退出状态决定硬件操作是否合法。

本章结论
--------

Linux 设备模型把不同总线中的实例统一为 ``struct device`` 层级，由 bus 完成匹配、driver 建立能力、class 提供功能视图，并用引用与 release 分离可见性撤销和最终释放。
