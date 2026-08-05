第120章：设备生命周期故障与 Driver Core 诊断
=============================================

本章必须记住
------------

#. 设备生命周期故障的本质是：绑定状态、对象引用、硬件可用性和异步执行没有在同一时间线中正确收束。
#. 分析任何设备 UAF、泄漏或 remove 卡死前，先列出该设备向外发布的全部入口。
#. 外部入口包括 class device、字符/块设备节点、网络接口、sysfs 属性、debugfs、IRQ、timer、work、DMA、NAPI、回调表和子设备。
#. Probe 失败处理的是半初始化对象，remove 处理的是已经成功发布并可能并发使用的对象，两类清理难度不同。
#. Probe 每成功一步，就增加一个新的回滚责任；资源申请和发布顺序必须明确记录。
#. 失败回滚通常按成功步骤逆序执行，因为后申请资源经常依赖先申请资源。
#. 纯内部资源、异步回调资源、用户可见接口和引用资源应分组分析，不能只写一串释放函数。
#. 私有内存和 MMIO 属于内部资源；IRQ、timer、work、NAPI 和 DMA completion 属于异步资源。
#. Netdev、cdev、block disk、input device 和 sysfs 属性属于外部可见入口。
#. ``get_device()``、模块引用、打开 fd、子对象 parent 引用和 kobject 引用决定最终内存何时释放。
#. Driver core 负责调用 probe 并根据返回值建立或拒绝绑定，不知道驱动内部资源依赖。
#. Probe 返回失败前，驱动必须撤销自身已完成的硬件与子系统初始化。
#. ``devm_*`` 只能自动归还挂在 devres 上的资源，不会自动注销业务接口、停止 DMA 或取消任意异步状态机。
#. Managed IRQ 最终会释放 IRQ，但驱动仍可能需要先停止硬件中断源和同步业务 work。
#. Probe defer 前应尽量不发布用户接口；否则每次重试都增加重复注册和残留状态风险。
#. ``dev_set_drvdata()`` 后失败时，应根据后续路径是否可能观察该指针决定何时清除，不能只在最后随意置空。
#. 错误路径必须保留最初失败原因，不能因清理函数返回值覆盖真正 probe 错误。
#. Remove 的第一步不是释放内存，而是建立单向退出状态，例如 dying、removed、stopping 或 disconnected。
#. 所有用户入口、IRQ、work、timer 和数据路径必须在访问硬件前检查统一退出状态。
#. Remove 应先阻止新请求，再撤销外部入口，然后同步已有执行，最后释放底层资源。
#. 先释放私有对象、后注销 netdev/cdev/sysfs 会让旧入口调用悬空回调。
#. 先释放 DMA ring、后同步 IRQ 会让迟到 completion 访问已释放描述符。
#. 先 unmap MMIO、后停止 work 会让工作线程访问失效寄存器地址。
#. 先释放模块代码、后结束打开文件操作会让 ``file_operations`` 指向已卸载文本。
#. 打开句柄需要把“软件对象寿命”和“硬件可用性”分开。
#. 设备移除后，旧 fd 可以因引用仍让私有对象存活，但后续 read/ioctl 必须返回断开或不可用错误。
#. Remove 不应无条件等待所有用户永久关闭 fd，否则恶意或失控进程可让设备解绑永远阻塞。
#. 常见设计是撤销新 open，设置 disconnected，保留对象到最后 fd release，再释放最终存储。
#. ``file->private_data`` 保存裸私有指针时，open 必须取得能覆盖整个 fd 生命周期的引用。
#. Release 文件操作负责归还该引用，设备 remove 只撤销硬件能力和创建者引用。
#. Workqueue 路径必须区分 ``cancel_work_sync()`` 与 ``flush_work()``：前者试图取消待执行并等待运行实例，后者确保已排队工作执行完成。
#. 自重排 work、delayed work 和跨 workqueue 链需要额外停止标志，单次 cancel 不能保证不会再次排队。
#. Timer 应使用同步删除接口，确保 callback 不再运行；timer callback 若重新启动自己，也需要退出状态配合。
#. ``free_irq()`` 通常包含必要同步，但共享 IRQ、threaded IRQ 和硬件仍在触发时仍需先关闭设备中断源。
#. ``synchronize_irq()`` 只等待指定 IRQ 当前 handler，不能停止硬件继续产生新中断。
#. NAPI disable、tasklet kill、thread stop、completion wait 分别收束不同执行对象，必须按真实路径选用。
#. DMA teardown 应阻止新映射和提交，停设备或队列，收束在途传输，再 unmap 和释放 buffer。
#. 设备物理消失后无法保证硬件响应停止命令，驱动仍要保证 CPU 侧对象和映射不会被迟到事件破坏。
#. IOMMU 可以限制错误 DMA 的破坏范围，但不能替代驱动正确停止和解除映射。
#. RCU 读者、引用计数持有者和异步回调是三种不同延寿机制，teardown 必须逐一收束。
#. 从全局索引摘除对象后，新查找停止；现有 RCU 读者仍需 grace period；独立引用仍需归零。
#. ``synchronize_rcu()`` 不等待普通 refcount、work、timer、DMA 或打开 fd。
#. 引用计数只保留内存，不停止硬件和 callback；把 refcount 当 remove 同步会产生长期僵尸对象。
#. Reference leak 表现为 release 不执行、sysfs/模块残留、设备对象长期存在或模块无法卸载。
#. Use-after-free 表现为 remove 后的 IRQ、work、sysfs、文件操作、PM 或上层 callback 访问旧对象。
#. Double put、错误所有权转移和失败路径重复释放会让对象过早进入 release。
#. 缺少 put、异常返回遗漏 cleanup、循环引用和子对象未注销会造成泄漏。
#. Parent-child 引用、device link、class device、driver data 和 bus private object 可能形成多层对象链，必须逐层标明最终释放者。
#. Sysfs 目录消失不证明对象已释放；对象仍可因打开属性、父子关系或其它引用存活。
#. Sysfs 目录残留也不必然是引用泄漏，可能是设备对象按设计仍存在但未绑定驱动。
#. Driver ``remove`` 返回后，不应再有驱动主动访问设备资源的异步路径；最终对象 release 可以稍后发生。
#. Release 回调执行时不应第一次处理复杂硬件停止，它只适合完成最后存储和从属对象释放。
#. Suspend/resume 与 remove 可能形成状态竞态，driver core 和 PM core 会提供框架锁，但驱动仍需保护私有状态。
#. Runtime PM work、autosuspend timer 和 resume request 都可能在解绑附近活动，remove 前应禁用或收束 PM 路径。
#. Shutdown、panic、kexec、热拔插和模块卸载的可用上下文不同，不能假设都走完整 remove。
#. 错误恢复 reset 也会暂时停止和重建硬件资源，不能与永久 remove 状态混用。
#. Reset 后旧 completion、旧 generation 和新 queue 可能发生 ABA，命令或对象应有 generation/epoch 验证。
#. Probe/remove 日志必须包含稳定设备身份，例如 PCI BDF、USB port path、platform name、dev_t 或 bus address。
#. 只记录 ``eth0``、``sda`` 等易变化名称不足以关联重插、重命名或多实例。
#. ``/sys/devices`` canonical path 用于确认 parent、bus、driver 和 class 关系。
#. ``/sys/bus/<bus>/devices`` 与 ``drivers`` 用于确认设备是否被发现、是否绑定和绑定到谁。
#. ``/sys/module/<module>/holders`` 等模块信息可帮助判断模块为何无法卸载，但不覆盖所有内部引用。
#. ``dmesg`` 应按绝对时间和设备身份排序，重点寻找 probe、defer、bind、remove、timeout、reset 和 release 前后的事件。
#. Dynamic debug 可对 driver core 或目标驱动启用细粒度日志，控制文件和语法以当前内核为准。
#. Dynamic debug 会增加日志和时序扰动，应按模块、函数或格式短时启用。
#. Ftrace function graph 可观察 probe/remove 调用链，但高频驱动路径需要过滤以避免过载。
#. Tracepoint、eBPF 和 kprobe 可追踪 device/driver 事件，具体事件和结构字段属于版本敏感接口。
#. KASAN 用于发现 UAF、越界和 double free；报告中的 alloc/free/use 栈要映射回设备生命周期阶段。
#. KCSAN 用于发现数据竞争，但报告竞争不自动说明对象已经 UAF，仍需分析状态和引用。
#. KMSAN 关注未初始化值，可能揭示 probe 半初始化字段被回调读取。
#. kmemleak 可发现部分不可达分配，无法发现仍被泄漏引用链保持可达的所有对象。
#. Lockdep 和 DEBUG_ATOMIC_SLEEP 可发现 remove/probe 中锁顺序、睡眠上下文和回调同步问题。
#. Refcount 调试可以发现饱和、下溢和部分非法增减，但对象语义和所有权仍需人工还原。
#. 故障注入应覆盖 probe 各步骤失败、IRQ/request 失败、固件超时、热拔插、reset 与并发 open。
#. 每个 probe 分配点都应能独立失败并完整回滚，不能只测试“全部成功”和“第一步失败”。
#. 热拔插压力测试应同时运行 I/O、sysfs 访问、PM、打开/关闭和模块 bind/unbind，观察竞态。
#. 生产环境不能无控制地反复解绑关键存储或网络驱动；应在隔离测试机和可恢复数据上验证。
#. 诊断 remove 卡死时，应抓取所有任务栈，确定等待的是 open count、work、IRQ、RCU、PM、firmware 还是硬件完成。
#. 诊断 UAF 时，先找第一次释放点，再找迟到访问路径，不要只修补崩溃位置的空指针检查。
#. 诊断泄漏时，先找应当执行但未执行的最终 release，再向上追踪未配对引用。
#. 正确修复必须改变所有权或同步协议，使错误路径不再可能发生，而不是延长固定 sleep 时间。
#. Teardown 不应使用任意 ``msleep`` 猜测硬件或 work 已结束，应使用 completion、flush、join、IRQ sync 或协议状态确认。
#. 稳定证据链是：注册/发布 → 引用取得 → 异步启动 → remove 阻止入口 → 同步执行 → put → release。
#. 稳定模型是“停止新访问、排空旧访问、最后释放”；精确 driver core 锁、tracepoint 和 helper 具有版本差异。

必背路径
--------

Probe 失败：

::

   分配私有对象
   → 申请 MMIO/clock/reset/IRQ/DMA
   → 初始化 work/timer/queue
   → 某一步失败
   → 不再发布新入口
   → 逆序停止异步路径
   → 释放 DMA、IRQ、MMIO 和依赖
   → 清除 drvdata
   → 释放私有对象
   → 返回原始错误

成功设备 Remove：

::

   设置 dying/disconnected
   → 阻止新 open、submit、sysfs 控制
   → 注销 netdev/cdev/disk/class 接口
   → 停止 queue 和新 DMA
   → 屏蔽硬件中断
   → synchronize/free IRQ
   → cancel/flush work、timer、NAPI
   → 等待 RCU 和在途请求
   → 释放硬件资源
   → put 创建者引用
   → 最后用户/子对象引用归零
   → release 宿主内存

打开 fd 跨越移除：

::

   open 查到设备对象
   → 取得对象引用
   → 保存 private_data
   → remove 设置 disconnected 并撤销新 open
   → 旧 read/ioctl 检查 disconnected 并返回错误
   → 用户 close
   → release file operation 归还引用
   → 最后引用触发对象 release

诊断 UAF：

::

   保存 KASAN/use 栈
   → 定位对象分配与 free 栈
   → 确认 free 属于 probe unwind、remove 还是 release
   → 找出迟到 IRQ/work/sysfs/fd/PM 回调
   → 检查是否缺少引用或同步
   → 修正入口关闭与等待顺序
   → 用热拔插和故障注入复测

诊断引用泄漏：

::

   确认设备已 remove/device_del
   → 观察 release 是否执行
   → 列出所有 get_device/kobject_get/module_get
   → 检查 open fd、子设备、work 和 sysfs
   → 查找遗漏 put 与循环引用
   → 验证最后引用归零
   → 确认 sysfs、模块和对象计数恢复

必须区分
--------

Probe unwind 与 Remove
   前者撤销半初始化资源；后者必须先撤销已发布接口并处理并发使用者。

对象引用与硬件可用性
   引用保留软件内存；removed 状态决定是否还能访问设备。

Sysfs 消失与 Release 执行
   可见性可以先撤销；最终释放要等全部引用结束。

Cancel 与 Flush
   Cancel 尝试阻止待执行工作并等待运行实例；flush 要求已排队工作完成，语义依具体对象。

RCU Grace Period 与全部使用者结束
   RCU 只等待对应读侧；普通引用、DMA、IRQ、work 和 fd 需独立收束。

Devm 自动释放与完整 Teardown
   Devres 归还挂载资源；业务接口、异步执行和对象引用仍由驱动负责。

一句话结论
----------

设备生命周期正确性的唯一可靠顺序是先撤销所有新入口，再同步并排空旧访问，最后让引用归零进入 release；任何颠倒都会形成泄漏、卡死或 use-after-free。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 24，Device Model, Kobject, Sysfs, Driver Core, and Device Lifetime；
* AIBook 章节：Chapter 120，Device Lifetime Bugs and Driver Core Diagnostics；
* 源文件：``docs/LinuxK/Part_24_Device_Model_Kobject_Sysfs_Driver_Core_and_Device_Lifetime/Chapter_120_Device_Lifetime_Bugs_and_Driver_Core_Diagnostics.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_24_Device_Model_Kobject_Sysfs_Driver_Core_and_Device_Lifetime/Chapter_120_Device_Lifetime_Bugs_and_Driver_Core_Diagnostics.md>`_。