第118章：Device、Driver、Bus 与 Class 关系
=========================================

核心知识点
----------

四类对象承担不同职责
   Device 表示实例，driver 表示控制代码，bus 表示匹配域，class 表示用户功能视图。它们处于同一 driver core，但不能互相替代。

Bus 决定候选关系
   PCI、USB、I2C、SPI 与 platform 等总线通过各自 ID、固件描述和协议规则实现 match，driver core 只负责组织和调用。

Match 不建立资源
   匹配成功只说明设备身份与驱动兼容。寄存器、IRQ、DMA、clock、queue 和上层接口都要等 probe 才建立。

Probe 建立 per-device state
   一个 driver 可服务多个实例，每个实例必须拥有独立私有对象。``dev_set_drvdata()`` 只保存指针，不管理其并发和释放。

Probe 具有依赖顺序
   常见顺序是确认依赖、使能设备、配置 DMA、映射寄存器、申请 IRQ、建立队列与异步对象，最后发布用户接口。

失败路径按逆序回滚
   后建立的对象通常依赖先建立的资源。Probe 任一步失败时，必须先撤销公开入口和异步路径，再释放底层资源。

Managed resource 只覆盖部分责任
   ``devm_*`` 可随解绑自动释放 MMIO、IRQ 等资源，不能自动注销 netdev、cdev、disk，也不能代替停止 DMA、work 和业务状态机。

Deferred probe 需要保持可重试
   返回 ``-EPROBE_DEFER`` 前应尽量避免发布复杂外部对象。重复 probe 必须面对干净、未残留的实例状态。

Remove 撤销 probe 建立的能力
   正确顺序是阻止新请求、注销外部接口、停止队列和 DMA、同步 IRQ 与异步执行，最后释放资源和私有状态。

打开句柄可能跨越 remove
   旧 fd 可以继续保护软件对象寿命，但 read、ioctl 等路径必须检查 disconnected 状态，不能因内存仍在就继续访问硬件。

Shutdown 与 remove 语义不同
   Shutdown 面向关机、重启或 kexec 前的安全停机，通常停止 DMA、中断和写缓存，不一定执行完整对象注销与内存回收。

PM 路径是另一组状态转换
   System suspend/resume 与 runtime PM 改变设备电源和可用状态。PM usage count 不是普通对象引用计数。

Class 不参与硬件匹配
   Probe 成功后，上层子系统可创建 block、net、input、tty 等 class 对象。一个硬件 device 可对应多个功能对象。

设备节点不能证明绑定成功
   ``/dev`` 名称由 devtmpfs/udev 和 class/dev_t 关系产生。判断绑定应检查 canonical device 的 ``driver`` 链接和 probe 结果。

解绑是完整生命周期操作
   手工 bind/unbind 会真实执行 probe/remove 和接口撤销，可能中断存储、网络或其它业务，不能当作普通属性修改。

绑定故障必须分阶段定位
   应区分设备未发现、无候选驱动、match 失败、probe defer、probe 失败，以及绑定后功能初始化失败。

关键路径
--------

匹配与绑定：

::

   Device 与 driver 注册到同一 bus
   → driver core 枚举候选关系
   → bus->match 检查总线身份
   → 调用 probe wrapper
   → 驱动分配 per-device state
   → 初始化硬件和异步路径
   → 注册 class/子系统接口
   → probe 返回 0
   → 建立绑定关系

Probe 失败回滚：

::

   某一步初始化失败
   → 停止继续发布
   → 注销已发布接口
   → cancel/flush work 与 timer
   → 停止 DMA 并同步 IRQ
   → 释放 queue、MMIO、clock 等资源
   → 清除 drvdata
   → 返回原始错误或 EPROBE_DEFER

Remove：

::

   设置 stopping / disconnected
   → 阻止新 open 与 submit
   → 注销 class 和上层功能对象
   → 停止硬件队列与 DMA
   → 屏蔽并同步 IRQ
   → 排空 work / timer / NAPI
   → 释放实例资源和私有状态
   → driver core 清除绑定

概念辨析
--------

* Device 与 Driver：Device 是具体实例；driver 是可服务多个实例的控制实现。
* Bus 与 Class：Bus 定义匹配规则；class 按用户功能组织对象。
* Match 与 Probe：Match 选择候选；probe 建立资源、状态和接口。
* Driver 对象与私有状态：驱动代码共享；每个设备的硬件状态必须独立。
* Remove 与 Shutdown：Remove 完整撤销绑定；shutdown 主要把硬件置于安全停机状态。
* Devm 与自动正确：Devm 管理部分资源释放，不能替代业务入口和异步路径收束。

本章结论
--------

Driver core 让 device 与 driver 在 bus 匹配域中相遇，probe 按实例建立资源和功能，class 将结果投影给用户空间，remove 再按反向依赖顺序撤销全部能力。
