第098章：High Refresh Rate, Display Power, Smoothness
====================================================

核心知识点
----------

* ``Refresh Rate`` 是显示硬件每秒刷新次数，``Frame Rate`` 是内容生产速度，``Touch Sampling Rate`` 是输入采样速度；三者共同影响用户感知流畅度，但属于不同系统层。
* 60Hz、90Hz、120Hz 的帧间隔约为 16.67ms、11.11ms、8.33ms。刷新率越高，同样的 UI、GPU 和合成工作越容易越过 deadline。
* 高刷新率体验依赖 ``Touch → Event Dispatch → App Update → Render → Buffer → Composition → Display`` 全链稳定，而非只依赖面板参数。
* ``Adaptive Refresh Rate`` 让系统根据滚动、动画、视频、静态页面、Always-On、电池和温度状态切换刷新率。
* 内容帧率和显示刷新率可以不同。24fps 视频在 120Hz 面板上可按整数倍重复显示；交互 UI 则更依赖低延迟和高频更新。
* Android 的 Surface frame-rate hint、Apple 的 display-link / frame-rate range 都只是调度输入；最终刷新率由系统结合全局 Surface、功耗、显示模式和硬件能力决定。
* 高刷新率提高 CPU 调度频率、GPU 工作量、DRAM/display 带宽和面板功耗，并可能更快触发 thermal throttling。
* ``Smoothness`` 同时取决于 frame deadline、frame pacing、刷新率切换和触摸反馈，不等于平均 FPS。

关键路径
--------

``Touch Sample → Input Dispatch → App State → UI / Render → GPU → Buffer → Compositor → Display Scanout``

刷新率策略：

``Content Frame Rate + Interaction State + Display Capability + Power + Thermal → System Refresh-Rate Decision``

120Hz 问题定位：

``Main Thread Budget → GPU Budget → Composition Budget → Frame Pacing → Actual Refresh Rate → Thermal / Power State``

概念辨析
--------

* ``120Hz display`` 不代表 App 一定运行 120fps；系统可能按内容、功耗和兼容性选择更低刷新率。
* ``Touch sampling rate`` 高于 display refresh rate 只能提高输入观测密度，不保证屏幕更快显示结果。
* ``Adaptive refresh`` 不是性能降级机制，而是显示体验与功耗之间的系统调度策略。
* ``Frame budget`` 是整条显示链共享的时间窗口，不是给 App 主线程独占的 8.33ms 或 16.67ms。
* 平均 120fps 仍可能不顺；帧间隔抖动和刷新率频繁切换同样会破坏体感。

本章结论
--------

高刷新率把显示系统的关键矛盾变成更短 deadline 与更高功耗之间的平衡。真正的流畅度来自输入、App、GPU、合成和显示策略共同保持稳定 frame pacing，并由系统在性能、电量和温度之间动态选择刷新率。