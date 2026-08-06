第140章：驱动中的电源管理故障模式
==================================

核心知识点
----------

PM Bug 是跨时间边界的状态失配
   I/O、IRQ、DMA、firmware、队列和电源状态跨过 suspend/resume 后没有回到一致状态，就会形成超时、数据损坏、死锁或虚假唤醒。

诊断先确定设备所处阶段
   Active、quiescing、suspended、resuming 和 partially restored 具有不同合法操作。只看设备对象或回调返回值不能证明硬件状态。

Resume 必须自底向上重建
   先恢复 power domain、bus、clock 和 MMIO，再恢复 firmware、寄存器、DMA ring、IRQ 与 queue，最后开放上层入口。

Lost State 不只包括寄存器
   低功耗或 reset 可能丢失 queue head/tail、descriptor owner、DMA address、MSI-X mask、firmware session、feature negotiation 和内部 generation。

Runtime PM Race 发生在提交边界
   新 I/O 与 runtime suspend 竞争时，PM usage 负责阻止断电，驱动私有锁负责让 submit、completion、reset 和 suspend 看到同一个状态。

Usage 必须覆盖完整在途请求
   请求写入 doorbell 后仍可能依赖 DMA、IRQ 和 completion。提前 put 会让设备在请求真正结束前进入低功耗。

Suspend 要证明设备已经沉默
   队列为空不等于硬件空闲。必须确认设备内部队列、bus mastering、descriptor owner、IRQ pending 和异步 worker 都已收束。

Wakeup Bug 有三种基本形态
   无法进入睡眠通常存在活动 source 或未完成工作；立即/频繁唤醒常来自旧 pending、极性或噪声；遗漏唤醒常来自 policy、寄存器、IRQ 或供电配置错误。

系统 PM 与 Runtime PM 状态会组合
   设备可能以 runtime suspended 状态进入 system suspend。重复关闭、重复恢复或 usage 泄漏常来自两个状态机没有统一入口条件。

正确性必须通过重复循环验证
   第一次恢复后能工作不够；第二次 suspend、反复 autosuspend、reset 后重试和 remove 竞态都必须回到同一稳定状态。

关键路径
--------

Resume 状态重建：

::

   恢复 power domain / bus / clock
   → 确认 MMIO 可访问
   → reset 或重新加载 firmware
   → 恢复配置寄存器
   → 重建 DMA ring 与 queue generation
   → 恢复 IRQ、MSI-X 与 affinity
   → 验证硬件 ready
   → 开放上层队列和用户入口

Runtime PM 安全提交：

::

   新 I/O 到达
   → pm_runtime_resume_and_get
   → 获取驱动状态锁
   → 检查 removing / suspending / hw_ready
   → 发布 descriptor 与 doorbell
   → 保持 usage 覆盖 in-flight request
   → completion 确认设备停止访问
   → mark_last_busy
   → put_autosuspend

第二次 Suspend 失败：

::

   比较首次 suspend 前后的稳定状态
   → 检查 usage 与 runtime_status
   → 检查 IRQ、DMA、queue generation
   → 检查 firmware session 与 wake pending
   → 检查首次 resume 是否恢复可再次 suspend 的条件
   → 定位第一个未回到初始状态的对象

概念辨析
--------

* PM Callback 成功与设备可用：回调返回是软件结果；硬件数据面必须真实恢复。
* Runtime PM Usage 与私有 I/O 锁：Usage 阻止电源转换；私有锁保护提交和状态竞态。
* Wakeup Policy 与硬件 Wake 配置：Policy 允许唤醒；驱动仍要正确 arm 设备和 IRQ。
* IRQ 同步与 DMA 收束：等待 handler 退出，不表示设备已经停止访问内存。
* 一次恢复成功与可重复状态机：可靠驱动必须在多轮 suspend/resume 后回到同一稳定状态。

本章结论
--------

驱动 PM 故障不是单个回调的错误，而是电源、寄存器、firmware、DMA、IRQ、队列和上层入口跨状态转换后的整体闭合失败；诊断应寻找第一个未恢复或未静止的对象。
