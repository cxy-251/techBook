第136章：系统睡眠、Suspend、Resume 与 Wakeup
===========================================

本章必须记住
------------

#. 系统睡眠是全机范围的电源状态转换，涉及用户任务、内核线程、设备、CPU、内存、平台固件和唤醒源。
#. System sleep 与 Runtime PM 不同：前者让整机进入低功耗状态，后者只让运行系统中的单个空闲设备暂时降功耗。
#. 用户态通常通过 ``/sys/power/state`` 请求 ``freeze``、``standby``、``mem`` 或 ``disk``。
#. ``mem`` 的实际模式由 ``/sys/power/mem_sleep`` 中的 ``s2idle``、``shallow``、``deep`` 选择决定。
#. ``s2idle`` 主要由内核冻结任务、暂停设备并让 CPU 进入 idle；``deep`` 通常还依赖平台固件和更深硬件状态。
#. Hibernation 会创建内存镜像并写入持久存储，恢复路径不同于保持内存内容的 suspend-to-RAM。
#. 一次 suspend 的稳定主线是：准备与冻结 → 设备分阶段 suspend → CPU/平台进入低功耗 → 唤醒 → 设备分阶段 resume → 解冻任务。
#. ``prepare``、``suspend``、``suspend_late``、``suspend_noirq`` 是不同阶段，不能把所有动作都塞入一个回调。
#. Resume 通常按 ``resume_noirq``、``resume_early``、``resume``、``complete`` 反向展开。
#. PM core 会先完成所有设备的某一阶段，再进入下一阶段，从而形成可诊断的全局边界。
#. 子设备和消费者通常应先 suspend，父设备、总线、供电域和 supplier 后 suspend；resume 顺序反向。
#. 设备父子关系、device link、PM domain、bus、class、type 和 driver 都可能参与实际回调选择。
#. 驱动文件里定义了回调，不代表 PM core 一定直接首先调用它；PM domain 或 bus 可以包裹驱动回调。
#. ``suspend`` 的核心责任是阻止新 I/O、收束在途工作、保存设备状态，并把硬件置于可恢复状态。
#. ``suspend_noirq`` 发生在常规设备 IRQ 已静止之后，适合必须在无普通 IRQ 并发下完成的硬件动作。
#. ``resume_noirq`` 必须先恢复后续中断和常规回调所依赖的最低层硬件条件。
#. Resume 回调返回成功前，后续上层请求所依赖的 MMIO、DMA ring、IRQ、固件和队列状态必须已经恢复。
#. Suspend 回调失败意味着系统尚未安全进入平台睡眠点，PM core 会回滚已经 suspend 的设备。
#. 回滚路径本身也必须正确，不能假设只有完整睡眠后才会执行 resume 类动作。
#. Freezer 的目标是阻止用户态和可冻结内核线程继续制造新状态变化。
#. 冻结任务失败、设备 suspend 失败、平台进入失败和恢复失败属于不同阶段，日志和修复方向不同。
#. 文件系统冻结、块 I/O 收束和设备队列停止解决不同层级，不能只靠冻结用户进程证明所有 I/O 已结束。
#. Wakeup capability 表示设备具备唤醒能力；wakeup policy 表示当前是否允许它唤醒系统。
#. ``device_may_wakeup()`` 只有在设备具备能力且策略启用时才成立。
#. ``/sys/devices/.../power/wakeup`` 是常见用户策略入口，``enabled`` 不表示设备已经正确配置硬件唤醒寄存器。
#. Wakeup source 不是普通 IRQ 的同义词；它还包含 PM core 的事件记账、唤醒窗口和策略状态。
#. 唤醒事件可能在 suspend 准备阶段到达，并使本次 suspend 被中止，而不是先睡下再恢复。
#. 驱动配置 wake IRQ 时必须区分工作状态下的普通事件处理和低功耗状态下的唤醒能力。
#. 设备作为 wake source 时，驱动可能保留有限电源、时钟或中断路径；这会增加睡眠功耗。
#. 系统立刻醒来可能来自真实外部事件、未清 pending、错误极性、噪声、wake 配置错误或已有活跃 wakeup source。
#. 不能仅凭“某 IRQ 计数增加”断定它是最终 wake reason；平台和固件可能重新编码或丢失部分信息。
#. Suspend-to-idle 的 wake source 与深度睡眠的 wake source 能力可能不同。
#. 深度睡眠能否进入取决于平台支持、固件、设备约束、CPU 状态和唤醒配置，不能只看 sysfs 字符串存在。
#. Console、调试输出和设备 trace 可能改变时序或阻止低功耗，应把观测扰动纳入结论。
#. ``pm_test`` 一类机制可以只测试 freezer、devices、platform 等阶段，帮助定位失败层级；具体接口依内核配置。
#. ``pm_async`` 可以改变设备 PM 回调的并行执行策略，故障复现时应记录其状态。
#. 异步 device PM 仍要尊重父子和依赖关系，并发只发生在允许的独立分支。
#. Suspend 与热插拔、driver unbind、runtime PM 和固件工作队列可能并发，驱动必须使用统一生命周期状态。
#. System suspend 前设备可能已经 runtime suspended；系统 PM 回调必须处理这种状态组合。
#. System resume 后设备不一定必须立即完全 active，PM core 和驱动可以恢复到与 runtime PM 一致的状态，具体策略具有版本差异。
#. ``direct_complete`` 等优化可能跳过部分设备回调，只有在设备状态和依赖条件满足时才允许。
#. 驱动不能假设每次 system suspend 都一定执行相同的 runtime 回调组合。
#. Suspend 保存的是恢复所需状态，不等于无条件保存每个寄存器；哪些寄存器会丢失由硬件电源域决定。
#. Resume 不能依赖 suspend 前仍然有效的 DMA address、队列指针或固件会话，除非硬件合同明确保证保留。
#. 低功耗状态可能使设备内部 firmware 重启，驱动需要重新上传、握手或恢复命令通道。
#. 系统 resume 的第一个错误请求通常能反映遗漏对象：TX timeout 指向队列/IRQ，固件超时指向内部控制器，MMIO 全 1 指向电源或总线状态。
#. 设备恢复后再开放用户入口和上层队列，能避免请求进入半恢复硬件。
#. Resume 失败时应保持上层入口关闭并返回明确错误，不能把设备标为 active 后继续静默丢请求。
#. Suspend 超时诊断应记录最后一个开始和结束的设备回调、阶段、耗时及依赖对象。
#. ``dmesg`` 中的 PM 日志给出全局阶段；设备私有日志用于说明硬件状态，二者要按同一时间线对齐。
#. Ftrace 的 power 事件和 function graph 可用于观察 device PM callback 和阶段耗时，事件名随版本变化。
#. ``/sys/kernel/debug/wakeup_sources`` 等接口可观察 wakeup source 统计，是否存在取决于配置和挂载状态。
#. ``/proc/interrupts`` 只能补充 IRQ 活动，不能单独证明低功耗状态、wakeup policy 或 resume reason。
#. Suspend 故障排查应一次只改变一个变量，例如禁用一个 wake source、关闭一个设备或切换 s2idle/deep。
#. 强制卸载驱动或写 sysfs 电源状态会改变系统，必须在可恢复实验环境执行。
#. 精确 PM 函数名、回调覆盖顺序和 sysfs 字段具有版本、总线与平台差异。
#. 稳定源码阅读顺序是：用户睡眠请求 → 全局准备/freezer → device PM 阶段 → 平台进入 → wake event → 反向 resume → 任务解冻。

必背路径
--------

系统 Suspend：

::

   写入 /sys/power/state
   → 解析 sleep state 与 mem_sleep 模式
   → PM notifier / console / filesystem 准备
   → 冻结用户任务和可冻结内核线程
   → dpm_prepare
   → dpm_suspend
   → dpm_suspend_late
   → dpm_suspend_noirq
   → CPU / syscore / platform enter
   → 等待 wake event

系统 Resume：

::

   平台返回
   → 恢复 CPU 与 syscore
   → dpm_resume_noirq
   → dpm_resume_early
   → dpm_resume
   → dpm_complete
   → 解冻任务与恢复 console
   → 用户态继续运行

设备 Suspend：

::

   阻止新提交
   → 停止上层队列
   → 等待/取消在途 I/O
   → 停止 DMA 与普通 IRQ
   → 保存会丢失的状态
   → 配置 wakeup
   → 关闭 clock/regulator/电源域
   → 返回成功

定位立即唤醒：

::

   确认实际进入 s2idle / shallow / deep
   → 查看 wakeup source 统计
   → 对齐 /proc/interrupts 与平台日志
   → 检查设备 pending 和触发极性
   → 检查 power/wakeup 策略
   → 一次禁用一个候选源复测
   → 区分 suspend 被中止与真正睡下后唤醒

必须区分
--------

System Sleep 与 Runtime PM
   前者协调全机状态；后者在系统运行时控制单个设备。

Wakeup Capability 与 Wakeup Policy
   Capability 是硬件/驱动能力；policy 是当前是否允许其唤醒。

Suspend Failure 与 Resume Failure
   前者阻止进入低功耗；后者发生在低功耗返回后的状态重建。

IRQ 静止与 DMA 停止
   无 handler 执行不表示设备已停止访问内存。

回调返回与硬件完成
   回调成功必须建立下一阶段所需硬件事实，不能只更新软件状态。

一句话结论
----------

系统睡眠是一场按依赖分阶段执行的全局静止与恢复协议，任何设备只有在 I/O、DMA、IRQ、固件状态和 wakeup 配置全部闭合后才具备可恢复性。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 28，Power Management, Hotplug, Firmware Loading, and Runtime PM；
* AIBook 章节：Chapter 136，System Sleep, Suspend, Resume, and Wakeup；
* 源文件：``docs/LinuxK/Part_28_Power_Management_Hotplug_Firmware_Loading_and_Runtime_PM/Chapter_136_System_Sleep_Suspend_Resume_and_Wakeup.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_28_Power_Management_Hotplug_Firmware_Loading_and_Runtime_PM/Chapter_136_System_Sleep_Suspend_Resume_and_Wakeup.md>`_。