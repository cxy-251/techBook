第137章：Runtime PM 与设备空闲状态
==================================

本章必须记住
------------

#. Runtime PM 在系统仍运行时控制单个设备的低功耗状态，不冻结全机任务，也不等同于 system suspend。
#. Runtime PM 的对象是 ``struct device``，核心状态位于 ``dev->power``，实际动作由 PM core、bus、PM domain 和驱动共同完成。
#. 驱动访问硬件前必须先证明设备处于 active 状态，常见入口是 ``pm_runtime_resume_and_get()``。
#. 访问结束后通常调用 ``pm_runtime_mark_last_busy()``，再调用 ``pm_runtime_put_autosuspend()`` 释放使用引用。
#. Runtime PM helper 的 get/put 是设备使用区间协议，不是普通对象引用计数的替代品。
#. ``usage_count > 0`` 表示仍有登记使用者，PM core 不应让设备 runtime suspend。
#. ``usage_count == 0`` 只表示没有登记使用者，不自动证明私有队列、DMA、IRQ、子设备和外部依赖已经空闲。
#. Runtime status 是 PM core 对设备状态的判断，常见阶段包括 active、suspending、suspended 和 resuming。
#. 软件 runtime status 必须与硬件真实状态保持一致，否则 helper 会在错误前提下跳过 resume 或重复 suspend。
#. 驱动在 probe 后应根据硬件实际状态设置初始 runtime status，再启用 Runtime PM。
#. ``pm_runtime_enable()`` 只启用框架，不会自动证明设备已经可安全 autosuspend。
#. ``pm_runtime_disable()`` 也不自动把已 suspended 设备恢复为 active；退出路径必须明确硬件最终状态。
#. Autosuspend 用最后忙碌时间和延迟避免设备在短请求间频繁 suspend/resume。
#. ``pm_runtime_mark_last_busy()`` 应放在最后一次真实硬件活动或完成处理之后，而不是请求刚提交时。
#. Autosuspend delay 是功耗与恢复延迟的权衡，不能只按设备“支持低功耗”就设为零。
#. ``/sys/devices/.../power/control`` 中的 ``auto`` 表示允许 Runtime PM，``on`` 表示保持设备工作态。
#. ``power/control`` 只影响 Runtime PM 策略，不取消 system suspend 回调。
#. ``runtime_suspend`` 的稳定职责是阻止新请求、收束在途 I/O、保存必要状态并让设备停止正常数据交换。
#. ``runtime_resume`` 的稳定职责是恢复电源、时钟、寄存器、队列、DMA 与 IRQ，并在返回前让正常 I/O 可用。
#. ``runtime_idle`` 只是空闲观察和策略入口，不能在未经证明时直接关闭仍有私有工作的硬件。
#. ``runtime_suspend`` 返回 ``-EBUSY`` 或 ``-EAGAIN`` 通常表示当前不能 suspend、未来可重试。
#. 其它错误可能使 PM core 记录 runtime error，后续请求需要明确修复或重新初始化状态。
#. Resume 失败通常比 suspend 失败更严重，因为上层请求已经需要硬件，设备却无法回到可用状态。
#. PM core 会序列化同一设备的 Runtime PM 回调，但不会替驱动序列化私有 I/O 提交、完成和 reset。
#. 驱动应使用私有锁或状态机，把“新请求到来”和“设备正在 suspend”放在同一判断边界中。
#. Runtime PM 引用应覆盖从第一次需要 MMIO/DMA 到最后一次完成处理和状态更新的完整区间。
#. 提交请求后立即 put，而 completion 尚未结束，可能导致设备在 DMA 或 IRQ 仍活跃时被关闭。
#. 错误路径漏掉 put 会让 usage counter 泄漏，设备长期保持 active。
#. 错误路径多执行一次 put 可能导致计数失衡，使 PM core 过早 suspend。
#. 异步请求、workqueue、timer、NAPI、poll 和 completion 都可能延长设备实际忙碌区间。
#. 设备中断到达不一定意味着设备仍需保持 active；完成路径何时 put 必须由请求所有权决定。
#. IRQ-safe Runtime PM 只适用于明确配置和允许的上下文，不能默认在任意硬中断中同步 resume。
#. 同步 helper 可能睡眠，不能在 spinlock、原子上下文或关闭中断的路径中随意调用。
#. 异步 PM request 只把转换排入 PM workqueue，不表示设备已经完成 suspend/resume。
#. 需要立即访问硬件的路径必须使用能等待 active 结果的正确 helper。
#. Active child 会阻止父设备 suspend，父子状态和 ``child_count`` 是 Runtime PM 约束的一部分。
#. 子设备访问父控制器、总线 bridge、clock provider 或 power domain 时，supplier 必须保持可用。
#. Device link 可表达 consumer/supplier 依赖，并帮助 PM core 安排 Runtime PM 和 system sleep 顺序。
#. 只依赖普通父指针并不能表达所有跨设备供应关系。
#. Generic power domain、bus callback、class/type callback 可能包裹驱动 Runtime PM 回调。
#. 驱动的 ``runtime_suspend`` 成功不一定意味着设备物理断电，可能只是进入逻辑 idle 或由上层电源域决定下一步。
#. Clock、regulator、reset 和 interconnect 资源的关闭顺序必须符合硬件依赖，恢复顺序反向。
#. Runtime suspended 状态下，普通 MMIO 访问可能返回错误值、触发总线故障或永久卡住，依平台而定。
#. 调试代码、sysfs show、ethtool、debugfs 和统计读取也必须遵守 Runtime PM 访问协议。
#. 不能因“只读寄存器”就绕过 resume，因为读取本身仍需要设备时钟和电源。
#. 驱动 remove 前应停止新 Runtime PM 请求，恢复或稳定设备状态，禁用框架，再释放硬件资源。
#. Managed 资源释放不会自动配平 Runtime PM usage counter，也不会停止 autosuspend work。
#. System suspend 与 Runtime PM 会组合：设备在 system suspend 开始时可能已 runtime suspended。
#. System PM 回调应处理 active 与 runtime-suspended 两种入口状态，不能无条件重复关闭硬件。
#. Resume 后是否保持 runtime suspended 取决于 PM core 和设备策略，具体优化具有版本差异。
#. Runtime PM 与设备热拔插并发时，remove 必须先让新 get 失败，再等待现有使用者和回调结束。
#. Runtime PM 与固件加载并发时，固件上传期间设备必须保持 active，异步回调也必须持有设备生命周期。
#. ``runtime_active``、``runtime_suspended`` 等 sysfs 状态是 PM core 视图，不是完整硬件证明。
#. ``power/runtime_status``、``runtime_active_time``、``runtime_suspended_time`` 等字段是否存在取决于内核版本和配置。
#. ``dmesg`` 可以显示 callback 错误和 PM 状态修复，不能单独证明每次 get/put 是否配对。
#. Ftrace power 事件、函数图和驱动 tracepoint 可还原 suspend/resume、I/O 和 completion 的时间关系。
#. 使用 lockdep、DMA debug、KASAN 等工具只能补充发现并发和生命周期问题，不能替代 PM 状态机审查。
#. 诊断设备不再 autosuspend 时，应检查 usage counter、active child、pending request、autosuspend delay 和 last_busy。
#. 诊断频繁抖动时，应检查请求间隔、delay、错误重试、统计读取和后台轮询。
#. 诊断 resume 后首个请求失败时，应检查电源/clock、寄存器、DMA ring、IRQ、firmware 和队列开放顺序。
#. 诊断设备在 suspend 中超时时，应检查未完成 I/O、长期引用、worker、timer 和 consumer 依赖。
#. 修改 ``power/control``、autosuspend delay 或手工 unbind 会改变设备状态，应在可恢复环境实验。
#. 精确 helper 返回约定、PM core 字段和 callback 选择顺序具有版本与总线差异。
#. 稳定源码阅读顺序是：I/O get → runtime status/usage → 硬件访问 → completion → last_busy → put → autosuspend → callback → 下一次 resume。

必背路径
--------

一次 Runtime PM I/O：

::

   I/O 到达
   → pm_runtime_resume_and_get
   → 等待设备 active
   → 获取驱动私有锁
   → 检查 hw_ready / removing
   → 编程 MMIO、DMA 或队列
   → 释放私有锁
   → completion 完成最后硬件访问
   → pm_runtime_mark_last_busy
   → pm_runtime_put_autosuspend

Autosuspend：

::

   usage_count 归零
   → 记录 last_busy
   → 等待 autosuspend_delay
   → 检查 active child / pending request
   → 调用 runtime_idle 或 runtime_suspend
   → 停止新请求与在途工作
   → 关闭硬件依赖
   → runtime_status = suspended

Runtime Resume：

::

   新使用者执行 get
   → PM core 发起 runtime_resume
   → 恢复 power domain / bus / clock
   → 驱动恢复寄存器与 firmware 状态
   → 恢复 DMA ring 和 IRQ
   → 标记 hw_ready
   → 返回成功
   → I/O 路径继续

安全 Remove：

::

   设置 removing 并拒绝新 I/O
   → 取消 autosuspend 与异步 PM 请求
   → 等待 usage 与在途 I/O 收束
   → 必要时恢复设备以执行安全停止
   → 停止 DMA / IRQ / worker
   → pm_runtime_disable
   → 修正最终 runtime status
   → 释放资源和对象

必须区分
--------

* Usage Counter 与对象引用：Usage 表示设备当前电源使用者；普通引用保证软件对象存活。
* Runtime Status 与硬件真实状态：PM core 状态是软件判断；驱动必须让硬件事实与其一致。
* Autosuspend 请求与 Suspend 完成：请求只表示未来允许转换；回调成功后才进入 suspended 状态。
* PM Core 串行化与驱动 I/O 串行化：PM core 保护回调；私有队列和提交竞态仍由驱动处理。
* 设备 Active 与上层队列开放：硬件恢复是前提；上层入口必须在全部依赖恢复后才能开放。

一句话结论
----------

Runtime PM 是围绕单设备使用区间建立的有界状态协议：每次硬件访问都必须由 get/put、私有 I/O 状态、父子依赖和完整 suspend/resume 回调共同证明安全。
