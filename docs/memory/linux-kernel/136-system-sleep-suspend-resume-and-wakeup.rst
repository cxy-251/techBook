第136章：系统睡眠、Suspend、Resume 与 Wakeup
===========================================

核心知识点
----------

系统睡眠是全局状态转换
   System sleep 同时协调任务、设备、CPU、内存与平台固件；Runtime PM 只控制运行系统中的单个空闲设备。

睡眠状态具有不同保留边界
   ``s2idle`` 主要依赖内核冻结和 CPU idle，``deep`` 进入更深的平台状态，hibernate 则把内存镜像写入持久存储后断电。

设备 PM 按阶段推进
   Suspend 通常经过 prepare、suspend、late、noirq；Resume 按 noirq、early、resume、complete 反向恢复。全局阶段边界使依赖和失败可定位。

依赖关系决定顺序
   子设备与 consumer 通常先暂停，parent、supplier、bus 和 power domain 后暂停；恢复顺序相反。Device link 可表达 parent 关系之外的供应依赖。

Freezer 只阻止新的任务活动
   冻结用户任务和可冻结内核线程不能自动排空块请求、DMA、IRQ、workqueue 或设备内部队列，各层仍需自己的静止协议。

Suspend 回调必须建立可恢复状态
   驱动要关闭新入口、收束在途 I/O、停止 DMA 与普通中断、保存会丢失的状态，并配置所需 wake path。

Resume 回调必须重建完整数据面
   电源、时钟、MMIO、firmware、DMA ring、IRQ 和队列都恢复后，才能重新开放上层请求。对象存在不等于硬件已经可用。

失败会触发分阶段回滚
   Suspend 中途失败时，PM core 会恢复已完成阶段的设备。驱动必须支持“未真正睡眠就被恢复”的路径，不能只实现完整睡眠循环。

唤醒能力、策略与事件不同
   Wakeup capability 表示设备具备能力，wakeup policy 表示当前允许使用；wakeup source 还包含事件记账和阻止系统继续睡眠的时序语义。

System PM 与 Runtime PM 会组合
   系统睡眠开始时设备可能已经 runtime suspended。驱动必须识别入口状态，避免重复断电、重复恢复或泄漏 Runtime PM usage。

关键路径
--------

系统 Suspend：

::

   用户请求 sleep state
   → 全局准备并冻结任务
   → 阻止新 I/O
   → dpm_prepare / suspend / late / noirq
   → 停止设备 DMA 与普通 IRQ
   → 配置 wakeup source
   → CPU、syscore 与平台进入低功耗

系统 Resume：

::

   Wake event 使平台返回
   → 恢复 CPU 与 syscore
   → dpm_resume_noirq / early / resume / complete
   → 重建设备电源、firmware、ring 与 IRQ
   → 重新开放上层队列
   → 解冻任务

立即唤醒诊断：

::

   确认实际 sleep mode
   → 区分 suspend 被中止与睡下后唤醒
   → 检查 active wakeup source
   → 检查设备 pending、trigger 与 polarity
   → 对齐 IRQ、平台 wake reason 和 PM 阶段
   → 定位第一个未静止的事件源

概念辨析
--------

* System Sleep 与 Runtime PM：前者协调全机；后者管理单设备使用区间。
* Suspend Failure 与 Resume Failure：前者阻止进入低功耗；后者发生在返回后的状态重建。
* Wakeup Capability 与 Policy：能力说明能否唤醒；策略决定当前是否允许。
* IRQ 静止与 DMA 停止：没有 handler 正在执行，不表示设备已经停止访问内存。
* 软件对象存活与硬件可访问：引用可保留对象；电源域关闭后 MMIO 和数据面仍不可用。

本章结论
--------

系统睡眠是按依赖分阶段执行的全局静止与恢复协议；只有任务、I/O、DMA、IRQ、firmware、设备状态和 wakeup 配置全部闭合，系统才具备可重复恢复性。
