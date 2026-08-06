第118章：Device、Driver、Bus 与 Class 关系
=========================================

本章必须记住
------------

#. ``device``、``driver``、``bus``、``class`` 处于同一 driver core，但分别表示实例、控制代码、匹配域和用户功能视图。
#. ``struct device`` 表示一个已被内核认识的设备实例；``struct device_driver`` 表示能处理某类设备的驱动实现。
#. ``struct bus_type`` 负责把同一匹配域内的 device 与 driver 进行匹配；具体身份规则由 PCI、USB、I2C、SPI、platform 等总线定义。
#. ``struct class`` 不负责硬件匹配，它把设备按 net、block、input、tty 等用户空间功能重新组织。
#. 一个 driver 对象可以绑定多个 device 实例；每个设备实例必须拥有独立的驱动私有状态。
#. 驱动整体的 ID 表、操作回调和模块代码可共享；MMIO、IRQ、DMA ring、queue 和运行状态不能在实例之间错误共享。
#. Device 先注册时，driver core 会尝试已有 driver；driver 后注册时，也会扫描已有未绑定 device。
#. Bus 的 ``match`` 回调只回答候选设备与驱动是否兼容，不建立硬件资源，也不证明设备可用。
#. PCI 匹配通常使用 vendor/device/class 等 ID；USB 常按 device/interface 描述符；platform、I2C、SPI 可能结合 OF、ACPI、名称或 bus-specific ID。
#. ``modalias`` 是设备身份到模块候选的用户空间表示，模块自动加载后仍需经过 match 和 probe。
#. Match 成功后，driver core 进入 probe 路径；只有 probe 成功返回 0，绑定才成立。
#. Probe 是驱动第一次拿到具体设备实例并建立 per-device state 的入口。
#. Probe 的稳定职责是确认能力、申请资源、初始化硬件、建立驱动私有对象并注册上层功能接口。
#. ``dev_set_drvdata()`` 或 bus-specific helper 只保存私有状态指针，不自动管理该对象的并发与释放。
#. Probe 内部资源通常存在依赖顺序：设备使能 → DMA mask → MMIO → IRQ → DMA/queue → work/timer → 上层接口。
#. 失败回滚必须按成功申请的逆序执行，确保后申请对象不再访问先申请资源。
#. 在任何用户可见接口发布前失败，通常只需撤销内部资源；发布后失败必须先撤销外部入口。
#. ``devm_*`` managed resource 将部分资源挂到 device 生命周期，减少错误路径，但不自动停止 work、DMA、上层注册对象或业务请求。
#. Devres 的释放时机依赖设备解绑，不等于每个中间失败点都能忽略子系统自己的注销要求。
#. ``-EPROBE_DEFER`` 表示 supplier 尚未准备好，driver core 会按策略稍后重试。
#. Probe defer 不是永久失败，也不应在已经注册用户接口或创建复杂子对象后才返回。
#. Deferred probe 过多或长期不结束时，应检查 regulator、clock、reset、PHY、firmware node、device link 和模块依赖。
#. ``remove`` 处理解绑或设备移除，目标是撤销 probe 建立的全部运行能力和 per-device state。
#. Remove 的正确总纲是先阻止新请求，再注销用户入口，再排空异步工作，最后释放硬件资源和私有内存。
#. 若上层仍可打开 cdev、netdev、block device 或 sysfs 控制接口，驱动不能先释放底层状态。
#. IRQ、timer、workqueue、tasklet、NAPI、DMA completion 和 threaded IRQ 都可能在 remove 调用栈之外继续运行。
#. ``free_irq()``、``synchronize_irq()``、``cancel_work_sync()``、``del_timer_sync()`` 等接口分别收束不同异步路径，不能互相替代。
#. 停止 DMA 的顺序通常是阻止新提交、通知硬件停止、等待或终止在途传输、同步 IRQ，最后解除映射并释放 ring。
#. 热拔插场景中硬件可能在 remove 前已经不可访问，清理代码必须能处理寄存器读写失败和迟到 completion。
#. 对象内存可以因打开句柄或引用继续存活，但所有路径必须通过 removed/dying 状态禁止新硬件访问。
#. ``shutdown`` 与 remove 不同：shutdown 主要在关机、重启或 kexec 前把设备置于安全状态，不一定执行完整对象释放。
#. ``shutdown`` 常需要停止 DMA、中断和设备写缓存，但系统即将结束时可能保留已分配软件对象。
#. Suspend/resume 处理系统睡眠和恢复；runtime suspend/resume 处理设备运行时电源状态。
#. 电源管理回调可能位于 driver、bus、class、PM domain 等多层，driver core 会按优先级和包装规则选择实际路径。
#. Suspend 前必须排空或冻结不允许跨睡眠保持的请求；resume 后必须恢复寄存器、queue、IRQ、DMA 和上层状态。
#. Runtime PM 的 usage count 与普通对象引用不是同一计数；对象存在不表示设备处于 active 电源状态。
#. Parent-child 关系、device links 和 PM domain 会影响 suspend/resume 与 remove 顺序。
#. Parent 关系表达设备层级；supplier-consumer link 表达功能依赖，两者可能不同。
#. Driver unbind 是生命周期操作，不是简单取消一个指针；它会触发 remove、sysfs 关系更新和功能接口撤销。
#. 手工 bind/unbind、driver override 和 new_id 等 sysfs 控制接口具有总线与版本差异，使用前必须确认业务空闲和数据安全。
#. Unbind 后设备对象可能仍存在于 bus 中并保持未绑定状态，等待其它驱动或重新绑定。
#. 设备移除和驱动卸载也不同：设备可以消失而模块仍服务其它实例，模块也可能因仍有绑定或引用而无法卸载。
#. 模块卸载前必须注销 driver，driver core 会先解绑所有实例；驱动私有异步路径和文件操作还需各自引用保护。
#. Class device 常在 probe 成功后由上层子系统建立，用于用户空间功能访问。
#. Class device 不一定与物理 device 一一对应，一个硬件实例可以注册多个 class 功能对象。
#. 例如 PCI 网卡硬件 device 与 ``net_device`` 不同；块控制器、磁盘、分区也属于不同对象层级。
#. Class 视图隐藏连接方式，便于用户空间按功能操作；物理拓扑和驱动匹配应回到 bus/device 视图。
#. ``device_create()`` 一类 helper 可创建 class device，但它仍需要 release、dev_t、parent 和销毁顺序正确。
#. 设备节点 ``/dev/*`` 常由 devtmpfs/udev 根据 class、dev_t 和 uevent 创建，它不是 driver binding 的直接证据。
#. Probe 成功日志不等于功能接口一定注册完成，驱动可能在后续异步初始化或固件加载阶段失败。
#. Probe 失败也不一定打印明确错误，返回码、deferred probe 状态和 dynamic debug 常比单条日志更可靠。
#. Sysfs 中 device 的 ``driver`` 链接是当前绑定证据；driver 目录中的设备链接提供反向视图。
#. ``drivers_probe``、``bind``、``unbind`` 等控制面是否存在及具体格式取决于总线实现。
#. Driver core 的公共锁保护绑定关系，但 probe/remove 内部业务对象需要自己的状态锁和引用协议。
#. Probe 和 remove 可能与用户空间、PM、热插拔和异步事件并发，驱动必须定义单一状态机。
#. ``dev->mutex`` 等核心锁不能被驱动任意替代或滥用，具体锁定规则应遵守 driver core 文档和源码。
#. 上层子系统通常还有自己的注册锁与 teardown 规则，driver core 只负责 device-driver 关系。
#. 错误排查应区分“设备没被发现”“无驱动候选”“match 失败”“probe defer”“probe 失败”“绑定后功能失败”。
#. 没有 device 对象时应回到固件描述、总线枚举和硬件发现；有 device 无 driver 时再检查匹配与模块。
#. 有 driver 链接但业务不可用时，应检查 probe 后的子系统注册、固件、IRQ、DMA、PM 和运行状态。
#. Remove 卡住通常意味着仍有 open handle、work、IRQ、DMA、子设备或上层子系统引用未收束。
#. Dynamic debug、driver core 日志、tracepoint、sysfs 和模块信息应按同一设备身份和时间线对齐。
#. 稳定源码阅读顺序是：bus-specific device → ``dev->bus`` → bus match → driver probe → drvdata → class/subsystem 注册 → remove/PM。
#. 稳定模型是“bus 选择候选，probe 建立能力，remove 撤销能力”；具体 wrapper、回调签名和锁顺序属于版本敏感实现。

必背路径
--------

设备与驱动匹配：

::

   Device 注册到 bus
   → Driver 注册到同一 bus
   → driver core 枚举候选关系
   → bus->match 读取 bus-specific ID
   → 匹配成功
   → 准备 probe 状态
   → 调用 bus/driver probe wrapper
   → 驱动实例 probe

Probe 建立设备：

::

   确认硬件和依赖
   → 使能设备与 DMA 能力
   → 映射寄存器/申请 clock、reset、regulator
   → 分配私有状态并设置 drvdata
   → 申请 IRQ、DMA ring、queue、work
   → 启动硬件
   → 注册 net/block/input/cdev 等功能接口
   → 返回 0 完成绑定

Probe 失败回滚：

::

   某一步返回错误
   → 停止后续发布
   → 注销已发布的用户接口
   → cancel/flush work、timer 和异步回调
   → 停止 DMA 并同步 IRQ
   → 释放 queue、ring、IRQ、MMIO 和资源
   → 清除 drvdata
   → 返回原始错误或 EPROBE_DEFER

Remove：

::

   driver core 请求解绑
   → 设置 stopping/dying
   → 阻止新 open、submit 和控制操作
   → 注销 class/subsystem 功能对象
   → 停止硬件队列和 DMA
   → 屏蔽并同步 IRQ
   → cancel/flush timer、work、NAPI
   → 释放资源和私有状态
   → 清除绑定关系

诊断未绑定设备：

::

   确认 device 已存在于 /sys/devices
   → 检查 subsystem/bus
   → 读取 modalias 和候选模块
   → 检查 driver 链接
   → 检查 deferred probe
   → 检查 probe 返回码和依赖
   → 检查手工 override/bind 状态
   → 验证功能 class 对象是否创建

必须区分
--------

* Bus 与 Driver：Bus 定义设备身份与匹配规则；driver 提供控制设备的代码和实例回调。
* Match 与 Probe：Match 只确认候选兼容；probe 申请资源并建立真正绑定能力。
* Driver 对象与 Per-device State：Driver 回调可共享；每个设备实例的寄存器、队列和运行状态必须独立。
* Remove 与 Shutdown：Remove 撤销对象绑定并完整 teardown；shutdown 主要在系统结束前停止硬件活动。
* Device 与 Class Device：Device 表达硬件/逻辑实例；class device 表达用户空间功能入口。
* Managed Resource 与自动生命周期正确：Devm 可自动释放资源；发布接口、异步 work、DMA 和业务引用仍需显式收束。

一句话结论
----------

Driver core 让 device 与 driver 在 bus 匹配域中相遇，probe 按实例建立硬件和功能状态，remove 再按相反依赖顺序停止入口、排空并发并撤销全部能力。
