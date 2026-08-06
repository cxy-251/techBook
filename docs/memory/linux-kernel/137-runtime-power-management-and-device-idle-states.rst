第137章：Runtime PM 与设备空闲状态
==================================

核心知识点
----------

Runtime PM 管理单设备使用区间
   系统保持运行时，PM core 根据设备是否被使用，在 active 与 runtime suspended 之间转换，不冻结全机任务。

Usage Counter 不是对象引用
   Runtime PM usage 表示设备当前电源使用者；普通 device/refcount 表示软件对象是否存活。两类计数解决不同问题。

硬件访问必须由 Get/Put 包围
   ``pm_runtime_resume_and_get()`` 应覆盖从首次 MMIO、DMA 或队列访问，到最后 completion 和状态更新的完整区间，不能在 doorbell 写完后提前 put。

软件状态必须对应硬件事实
   ``runtime_status`` 是 PM core 的判断。驱动若把已断电设备标为 active，或把仍运行设备标为 suspended，后续 helper 会在错误前提下执行。

Autosuspend 延迟关闭设备
   Usage 归零、``last_busy`` 已更新且延迟到期后，PM core 才尝试 suspend。延迟用于平衡功耗、恢复成本和短请求间抖动。

Runtime Suspend 必须证明设备真正空闲
   软件队列为空不够；还要确认在途 I/O、DMA、IRQ、timer、work、子设备和设备内部队列都已停止或可安全保留。

Runtime Resume 必须恢复完整能力
   电源域、clock、reset、寄存器、firmware、DMA ring 和 IRQ 都恢复后，回调才能成功返回并允许普通 I/O 继续。

PM Core 不替代驱动并发控制
   Core 可串行化同一设备的 PM 回调，但 I/O submit、completion、reset、remove 和调试读取仍需驱动私有锁与统一状态机。

设备依赖会限制 Suspend
   Active child、parent、supplier、device link、bus 和 generic power domain 都可能要求相关设备保持工作，单个驱动不能只看自身 usage。

退出路径必须终止 PM 活动
   Remove 要先拒绝新 get 和新 I/O，取消 autosuspend/异步 PM 请求，收束现有使用者，再禁用 Runtime PM 和释放硬件资源。

关键路径
--------

一次 Runtime PM I/O：

::

   I/O 到达
   → pm_runtime_resume_and_get
   → 等待设备 active
   → 在私有状态锁下检查 removing / hw_ready
   → 发布 MMIO、DMA 或队列请求
   → completion 完成最后硬件访问
   → pm_runtime_mark_last_busy
   → pm_runtime_put_autosuspend

Autosuspend：

::

   usage_count 归零
   → 记录 last_busy
   → 等待 autosuspend delay
   → 检查 child、supplier 与在途工作
   → runtime_suspend 阻止新请求
   → 停止 DMA、IRQ 和设备内部队列
   → 关闭 clock / regulator / power domain
   → runtime_status 进入 suspended

安全 Remove：

::

   设置 removing
   → 拒绝新 I/O 与 Runtime PM get
   → 取消 autosuspend 和异步 PM work
   → 等待 usage 与在途请求收束
   → 必要时恢复设备以执行安全停止
   → 停止 DMA、IRQ、worker
   → pm_runtime_disable
   → 释放资源与对象

概念辨析
--------

* Usage Counter 与对象引用：前者防止设备断电；后者防止软件对象释放。
* Runtime Status 与硬件状态：Core 保存软件状态；驱动必须让它与真实电源和数据面一致。
* Autosuspend 请求与 Suspend 完成：允许未来进入低功耗，不等于转换已经完成。
* PM 回调串行化与 I/O 串行化：Core 管理回调；驱动管理提交、完成与 reset 的竞态。
* Active 设备与开放队列：设备恢复是必要条件；上层入口要等所有依赖恢复后才能开放。

本章结论
--------

Runtime PM 是围绕单设备使用区间建立的状态协议；安全性取决于 usage、私有 I/O 状态、依赖关系和 suspend/resume 回调共同证明设备何时可以暂时消失、何时已经完整返回。
