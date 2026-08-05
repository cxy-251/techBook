第140章：驱动中的电源管理故障模式
==================================

本章必须记住
------------

#. 电源管理故障的核心是时间边界：I/O、IRQ、DMA、firmware 或队列状态跨过 suspend/resume 转换后失去一致性。
#. 排查 PM bug 必须先确定设备当前处于 active、quiescing、suspended、resuming 还是 partially restored。
#. 软件回调返回成功不等于硬件已经完全可用，必须检查后续请求依赖的所有对象是否恢复。
#. Resume failure 常表现为设备对象仍存在、上层接口也已开放，但第一批 I/O 超时或数据路径沉默。
#. Lost state 可能来自寄存器、DMA ring、queue head/tail、IRQ mask、firmware session、clock 或 power domain 未恢复。
#. Resume 应先恢复底层访问条件，再恢复设备私有状态，最后开放上层队列和用户入口。
#. 在 MMIO、DMA、IRQ 或 firmware 尚未准备好时开放队列，会让请求进入半恢复设备。
#. Suspend 前必须记录哪些状态会在目标低功耗状态中丢失，不能盲目保存全部寄存器或假设全部保留。
#. W1C、clear-on-read、volatile status 和 self-clearing 寄存器不能作为普通配置状态保存后原样恢复。
#. 硬件 reset 后旧 DMA address、descriptor generation、command token 和 firmware session 可能全部失效。
#. Resume 后复用 suspend 前的 ring 前，必须确认设备是否保留 ring 基址、owner 位和内部 consumer 指针。
#. Firmware 型设备可能需要重新加载 blob、重新握手和重新协商 feature。
#. MSI/MSI-X、INTx、IRQ affinity 和设备侧 interrupt mask 需要分别恢复。
#. 配置空间恢复、BAR 可访问和设备私有 MMIO 状态属于不同层级。
#. Resume 回调失败时，上层入口应保持关闭，设备状态应明确标记为不可用或进入受控 reset。
#. 错误路径不能一半恢复 queue、一半保持 IRQ 关闭，否则后续 retry 会叠加状态。
#. Runtime PM race 发生在系统仍运行时，I/O 提交与 runtime suspend/resume 同时竞争设备状态。
#. PM core 序列化 Runtime PM callback，不会自动序列化驱动私有提交、completion、reset 和 remove。
#. I/O 提交前应持有有效 Runtime PM usage，并在设备 active 后再访问 MMIO 或发布 DMA。
#. Usage 引用必须覆盖在途请求真正结束，而不是只覆盖“写完 doorbell”这一瞬间。
#. Completion 仍依赖设备 IRQ、DMA 或 worker 时，过早 put 可能让设备在请求未完成时 suspend。
#. Runtime suspend 必须先阻止新提交，再等待或取消旧请求，然后关闭 DMA、IRQ、clock 和电源。
#. 仅检查软件队列为空不够；还要确认设备内部 queue、descriptor owner 和 bus mastering 已停止。
#. Autosuspend 与新 I/O 竞态应由 PM usage 加驱动私有锁共同解决。
#. ``pm_runtime_resume_and_get()`` 成功后错误路径必须配对 put，否则设备永久保持 active。
#. Resume helper 失败后不能继续访问设备，即使旧软件状态仍标记 hw_ready。
#. Runtime PM 状态错误可能表现为 double resume、访问断电 MMIO、usage underflow 或永不 autosuspend。
#. Wakeup bug 分为无法进入睡眠、虚假/频繁唤醒和遗漏合法唤醒三类。
#. 系统无法睡眠可能来自活动 wakeup source、设备 callback 返回忙、pending IRQ、未完成 I/O 或用户任务冻结失败。
#. 立即唤醒可能来自未清 pending、错误 trigger polarity、设备仍在产生事件、噪声或平台固件报告。
#. Missed wake 可能来自 wakeup policy 未启用、设备 wake 寄存器未配置、IRQ 在错误阶段被 mask 或供电被完全关闭。
#. ``power/wakeup=enabled`` 只表示策略允许，不证明硬件 wake path 已建立。
#. 普通工作 IRQ 与 wake IRQ 可能是同一个 vector，也可能是独立资源，必须按总线和设备协议判断。
#. 配置 wake 后应清旧 pending，再 arm wake，避免把历史事件当新唤醒。
#. Resume 后应读取并清 wake reason，但读取某些状态寄存器可能有副作用。
#. Wakeup source 计数和平台 wake reason 可能不同，需按时间线交叉验证。
#. System suspend 与 Runtime PM 状态组合容易产生重复关闭或遗漏恢复。
#. 设备在 system suspend 开始时可能已经 runtime suspended，system callback 应识别并避免破坏 PM core 状态。
#. System resume 后设备可能继续由 Runtime PM 管理，不能无条件强制 active 并泄漏 usage。
#. Runtime PM 与 hot unplug 并发时，remove 要阻止新 get、等待 callback 和 in-flight I/O，再释放资源。
#. Runtime PM 与 firmware async callback 并发时，回调必须检查设备 generation 和 removing 状态。
#. PM callback 与普通用户 ioctl、sysfs、debugfs 和统计读取都可能竞争硬件访问。
#. 调试接口也必须取得 Runtime PM 引用，不能因“只是读取状态”绕过电源协议。
#. Suspend/resume 回调中的锁顺序必须避免与 I/O 路径、workqueue 和 PM core 形成死锁。
#. 在 PM callback 中等待一个仍需要同一设备 resume 或同一锁的 worker，会形成自依赖死锁。
#. Suspend 前 ``cancel_work_sync()``、``del_timer_sync()``、NAPI disable、queue freeze 等需按回调上下文选择正确顺序。
#. ``synchronize_irq()`` 等待 handler 退出，不会停止设备继续产生 IRQ，也不会停止 DMA。
#. Mask 设备中断源后可能需要 read-back，确认 posted MMIO write 已到达设备。
#. Disable IRQ 不能替代清设备 pending；重新启用时旧状态可能立即触发风暴。
#. 停止 DMA 后要等待 idle/ownership 返回，再 unmap/free buffer。
#. Reset 可能终止设备工作，但必须确认总线层面 DMA 已停止，不能立即复用旧内存。
#. Suspend timeout 常来自等待永远不会完成的请求、固件命令、设备 idle 位或下层 supplier。
#. 所有 polling 和 completion wait 都应有界，并在超时时保存关键状态。
#. PM callback 不应吞掉硬件错误并返回成功，否则故障只会延迟到第一批业务 I/O。
#. ``-EBUSY``、``-EAGAIN``、``-ETIMEDOUT``、``-EIO`` 应表达不同失败原因，错误码也是诊断合同。
#. Resume 后性能下降可能来自 IRQ affinity、queue mapping、offload、link state 或 Runtime PM policy 未恢复。
#. 电量异常可能来自设备从不 autosuspend、频繁抖动、错误 wake source 或 supplier 电源域始终 active。
#. 高频 suspend/resume 会放大寄存器恢复、firmware 重载和设备磨损/稳定性问题。
#. PM 故障常具有负载相关性：空闲测试成功，高 I/O 下因在途请求和 teardown 竞态失败。
#. PM 故障也常具有架构相关性：某平台更深电源状态会丢失更多设备状态。
#. ``/sys/power/state`` 和 ``mem_sleep`` 用于确认系统目标状态。
#. 设备 ``power/control``、runtime status、autosuspend delay 和 wakeup 属性用于确认单设备策略。
#. ``dmesg`` 应按 suspend 开始、最后成功 callback、失败 callback、回滚和 resume 顺序阅读。
#. Ftrace power 事件可以记录 device PM callback 起止和耗时，具体事件名随版本变化。
#. Function graph 可定位驱动回调内部卡点，但会增加时序扰动。
#. ``pm_test`` 可按 freezer、devices、platform、processors、core 等层级缩小 system suspend 问题，具体支持依配置。
#. Wakeup source debug、``/proc/interrupts``、ACPI/平台日志和设备寄存器 dump 应按同一时间戳对齐。
#. 寄存器 dump 必须避免读取 clear-on-read 或掉电不可访问寄存器。
#. 动态调试和 tracepoint 比在 IRQ/PM 热路径大量 ``printk`` 更可控。
#. 一次只禁用一个设备、wake source 或 PM 模式，才能建立可归因实验。
#. 禁用 Runtime PM 让故障消失只证明与电源状态转换相关，不直接证明驱动哪个回调错误。
#. 切换 s2idle/deep 结果不同，通常说明平台电源深度、固件或设备状态保留差异。
#. 只在第二次 suspend 失败，常指向首次 resume 没有完整恢复可再次 suspend 的状态。
#. 只在重复 runtime suspend 后失败，常指向 usage、状态机、ring generation 或资源重复启停不对称。
#. 只在设备移除后恢复流程崩溃，常指向迟到 PM work、firmware callback 或旧对象引用。
#. 建议建立状态快照：PM core status、usage、queue depth、DMA owner、IRQ enabled、firmware generation、clock/power 状态。
#. 状态快照应在 suspend 前、回调各阶段、resume 后首个 I/O 前后分别采集。
#. 精确 PM sysfs、debug option、callback 顺序和 helper 语义具有版本、平台和总线差异。
#. 稳定诊断顺序是：确认 PM 模式 → 定位失败阶段 → 找到第一个未恢复对象 → 对齐 I/O/IRQ/DMA 时间线 → 审查错误回滚与第二次循环。

必背路径
--------

Resume 状态重建：

::

   恢复 power domain / bus / clock
   → 确认 MMIO 可访问
   → reset 或重新加载 firmware
   → 恢复配置寄存器
   → 重建 DMA ring 与 queue generation
   → 恢复 IRQ/MSI-X 与 affinity
   → 确认硬件 ready
   → 开放上层队列和用户入口

Runtime PM 安全提交：

::

   新 I/O 到达
   → pm_runtime_resume_and_get
   → 获取驱动状态锁
   → 检查 removing / suspending / hw_ready
   → 发布 descriptor 和 doorbell
   → 保存请求为 in-flight
   → completion 确认设备结束访问
   → mark_last_busy
   → put_autosuspend

Wakeup 故障诊断：

::

   确认 wakeup capability 与 policy
   → 检查设备 wake 寄存器和旧 pending
   → 确认 IRQ trigger / polarity / mask
   → 观察 wakeup source 与平台 reason
   → 对齐 suspend 是否真正进入低功耗
   → 一次禁用一个候选 wake source
   → 复测 missed wake 与 immediate wake

第二次 Suspend 失败：

::

   比较首次 suspend 前状态
   → 检查首次 resume 恢复对象
   → 检查 usage counter 与 runtime status
   → 检查 IRQ、DMA、queue generation
   → 检查 firmware session 与 wake pending
   → 找到未回到初始状态的第一个对象

必须区分
--------

PM Callback 成功与设备可用
   回调返回是软件结果；硬件所需资源、队列和完成路径必须真实恢复。

Runtime PM 引用与私有 I/O 锁
   Usage 防止电源转换；私有锁保护请求和硬件状态竞态。

Wakeup Policy 与硬件 Wake 配置
   Policy 允许设备唤醒；驱动仍要正确编程设备和 IRQ。

IRQ 同步与 DMA 收束
   等待 handler 不表示设备停止访问内存。

第一次恢复成功与可重复循环
   正确 PM 驱动必须在多次 suspend/resume 后仍回到同一稳定状态。

一句话结论
----------

驱动 PM 故障不是单个回调问题，而是电源、寄存器、firmware、DMA、IRQ、队列和上层入口跨状态转换后的整体闭合失败。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 28，Power Management, Hotplug, Firmware Loading, and Runtime PM；
* AIBook 章节：Chapter 140，Power Management Failure Modes in Drivers；
* 源文件：``docs/LinuxK/Part_28_Power_Management_Hotplug_Firmware_Loading_and_Runtime_PM/Chapter_140_Power_Management_Failure_Modes_in_Drivers.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_28_Power_Management_Hotplug_Firmware_Loading_and_Runtime_PM/Chapter_140_Power_Management_Failure_Modes_in_Drivers.md>`_。