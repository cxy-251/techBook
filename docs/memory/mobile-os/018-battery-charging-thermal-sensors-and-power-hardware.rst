第018章：Battery, Charging, Thermal Sensors, and Power Hardware
==============================================================

核心知识点
----------

* Battery Gauge 把电压、电流、温度、充放电积分和老化模型转换成 state of charge、剩余容量和健康状态；用户看到的电量百分比是系统估算结果，不是单一电压读数。
* Charging IC 负责输入电源协商、恒流/恒压充电、温度与电压保护。插着充电器并不保证电池一定快速增长，系统负载本身会先消耗一部分输入功率。
* PMIC 把电池或外部电源转换成 CPU、GPU、DRAM、display、camera、modem、sensor 等硬件所需的电压轨，并参与 power domain、clock、sleep/wakeup 和保护状态管理。
* App 不直接控制充电电流、PMIC 或热阈值。硬件状态先经过 driver/firmware，再由系统电源与 thermal service 转成 App 可观察的 battery、low-power 和 thermal state。
* Thermal sensor 分布在 SoC、电池、modem、camera、USB/charging path 和机身表面等位置。系统关心的不是某一个温度数值，而是整机是否需要进入更强的降级等级。
* Thermal policy 通常使用 severity/state 抽象，把多个传感器和设备差异映射成 light、moderate、severe 等可执行状态，并使用滞回避免频繁升降级抖动。
* CPU、GPU、ISP、display、modem、camera 和 charging 都是常见功耗/发热热点。录像、游戏、5G 上传、高亮度屏幕和快充叠加时会快速消耗同一 thermal envelope。
* 降级应优先牺牲可延迟或可降低质量的工作，例如后台上传、模型推理、帧率、亮度和部分画质处理；核心用户操作通常获得更高优先级。
* Wakeup source 把电源硬件与后台执行连接起来。Push、网络、alarm、传感器等唤醒会恢复 power domain、CPU 与内存活动，因此系统会限制无意义的频繁唤醒。
* 电源状态会反向改变 App 行为：低电量、高温、弱网、充电状态和设备锁屏都可能使后台任务延后、网络受限、相机降级或性能下降。

关键路径
--------

电量状态：

::

   battery voltage / current / temperature
   → gauge and charging IC
   → kernel / vendor driver
   → system power service
   → battery percentage / charging state / policy
   → app-visible status

温控闭环：

::

   CPU / GPU / ISP / modem / battery heat
   → thermal sensors
   → thermal HAL / service
   → severity decision
   → frequency / brightness / camera / network / background limits
   → temperature falls
   → hysteresis permits recovery

后台唤醒：

::

   push / alarm / sensor / radio event
   → retained low-power hardware
   → wakeup source
   → PMIC restores required power domains
   → kernel schedules system service
   → limited app work window
   → return to idle

概念辨析
--------

* **Battery percentage 与 raw voltage**：百分比是 gauge 基于电池模型计算的状态估计，不等于电压线性换算。
* **Charging 与 system power**：外部电源既供系统当前负载，也给电池充电；高负载时“正在充电”仍可能增长很慢。
* **Power limit 与 thermal limit**：前者关注能量/电流预算，后者关注热积累与安全，两者可能同时触发不同策略。
* **Thermal sensor 与 thermal state**：App 通常拿到抽象状态，真正策略来自多个传感器、硬件限制和系统阈值的组合。
* **Wake lock / background request 与无限运行**：能唤醒或请求后台能力不代表可以长期保持高功耗状态，系统仍会按预算和策略裁决。

本章结论
--------

移动电源系统是一个从 Battery Gauge、Charging IC、PMIC 和 thermal sensor 向上反馈到系统策略的闭环。理解发热、降频、亮度下降、相机降级或后台任务延迟时，应把供电、充电、热状态、wakeup 和 App 优先级放在同一条路径上分析，而不是把它们视为互不相关的系统设置。