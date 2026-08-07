第004章：Mobile Platform Constraint Model
=========================================

核心知识点
----------

* 移动平台约束模型决定一次能力请求是立即执行、延后、降级、拒绝还是终止。判断输入不仅有 API 参数，还包括电量、温度、隐私、网络、前后台状态和用户设置。
* Battery budget 是整机预算，不是单个 App 的局部功耗。CPU、GPU、display、camera、GNSS、modem、sensor、storage 和后台唤醒会共同消耗有限能量。
* 前台用户正在等待的任务通常获得更高优先级；后台同步、图片上传、索引和维护任务更适合批处理、合并唤醒或等待合适网络与充电条件。
* Doze、App Standby、JobScheduler、WorkManager、Background Tasks 等机制都说明：后台执行是系统调度资源，不是 App 自己决定的持续运行权。
* Thermal envelope 约束的是热量和安全状态。高负载时系统可降低 CPU/GPU/ISP 频率、帧率、相机质量、充电速度和后台工作量。
* Thermal throttling 是跨层状态：硬件传感器产生温度信息，HAL/kernel 汇总，system service 形成状态，Framework/App 再根据状态主动降级工作负载。
* 持续环境感知依赖低功耗策略。步数、motion、location 等应尽量利用 sensor hub、批处理、低采样率、显著变化触发和系统融合，而不是让主 CPU 长时间保持唤醒。
* Camera、microphone、location、photos、Bluetooth 等隐私敏感能力不仅有 permission，还可能有后台限制、状态指示器、近似精度、全局开关和撤销路径。
* 蜂窝与 Wi-Fi 的连接成本不同。弱蜂窝信号、漫游、计费网络和低数据模式都会影响后台传输、重试、批处理和上传时机。
* Wakeup 是昂贵资源。alarm、push、location、Bluetooth、job、network retry 都可能唤醒系统，平台会限制频率并尽量合并工作。
* Hardware state、service ownership、app lifecycle 和 user settings 共同决定能力结果。单独检查权限无法解释大量移动端“同样代码有时能跑、有时不能”的现象。
* App 应按核心价值排序降级：必须持续的记录优先保留，可推迟的上传、分析、动画和高质量处理优先收缩。

关键路径
--------

一次移动能力裁决：

::

   app request
   → caller identity + lifecycle
   → permission / privacy state
   → battery and thermal state
   → connectivity and data policy
   → resource ownership
   → execute / defer / downgrade / deny / stop

后台任务：

::

   background work request
   → scheduler records constraints
   → wait for execution window
   → network / charging / idle conditions satisfied
   → run within granted budget
   → finish or receive stop reason

温控降级：

::

   temperature rises
   → hardware sensors report pressure
   → kernel / HAL / thermal service updates state
   → platform reduces workload budget
   → app and system services degrade quality or defer work

概念辨析
--------

* **Battery 与 thermal**：Battery 关注能量和续航，thermal 关注热量积累与安全；两者经常同时改变资源策略。
* **后台执行与立即执行**：后台任务通常表达“最终需要完成”，系统决定具体执行时机。
* **传感器持续能力与持续 CPU 运行**：低功耗传感器、sensor hub 和批处理可在主 CPU 休眠时继续感知。
* **权限允许与策略允许**：用户授权并不取消后台、温控、网络和资源占用限制。
* **网络可达与适合传输**：有网络连接不等于系统会立即允许大流量后台上传。

本章结论
--------

移动 OS 的核心不是让所有合法请求立即执行，而是在有限电量、散热、隐私、网络和后台预算下保持整机可用。理解系统行为时，应把 battery、thermal、sensor、privacy、connectivity 和 lifecycle 作为每次能力调用的实时输入，并沿系统策略寻找最终是执行、延迟、降级还是拒绝。