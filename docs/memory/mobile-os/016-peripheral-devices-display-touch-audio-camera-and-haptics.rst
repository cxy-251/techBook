第016章：Peripheral Devices Display, Touch, Audio, Camera, and Haptics
=====================================================================

核心知识点
----------

* Display、Touch、Audio、Camera、Haptics 都属于由系统集中控制的外设能力。App 看到 API 和回调，底层实际由 controller、firmware、driver、system service 和硬件状态共同决定结果。
* Display 路径从 App buffer 进入 compositor，再到 display controller 和 panel；刷新率、亮度、HDR、自动亮度、省电和 thermal policy 都能改变最终输出。
* Touch 路径是 ``touch controller → firmware filter → interrupt → kernel input → system input service → target window → UI thread``。输入延迟既可能来自硬件采样，也可能来自 App 主线程忙碌。
* Audio 路径由 microphone/speaker、codec、DSP、mixer、route policy 和系统音频服务共同组成。播放或录音 API 成功，不代表最终 route、focus 和设备占用一定满足预期。
* Camera module 把 sensor、lens、OIS、flash、校准数据和 ISP 接口组合成一个系统能力；真正开放给 App 的范围仍由 camera service、HAL、权限和并发策略决定。
* Haptic engine/vibration motor 由系统把 pattern、强度、时长和交互策略转换成硬件驱动信号。触觉反馈是系统交互时间线的一部分，不只是“开马达”。
* 多外设经常在同一次用户动作中并行：点击快门会同时触发 touch、UI frame、haptic、audio、camera capture 和 display update。体验问题要按时间线检查多个通道，而不是只看某个 API。
* 外设共享 CPU、DRAM、power、thermal 和系统服务资源。相机录像时的显示、音频、触觉和网络行为都可能被整机预算间接影响。
* 系统服务负责资源所有权和仲裁。App 崩溃、退后台、权限撤销、route change 或设备断开时，服务端必须回收 session 并重新分配硬件。

关键路径
--------

快门交互：

::

   finger touches screen
   → touch controller / input service
   → app UI callback
   → camera capture request
   → haptic + audio feedback
   → camera module / ISP produces frame
   → preview or result buffer
   → display compositor / panel

音频路由：

::

   app creates playback / record stream
   → audio framework
   → audio policy / focus arbitration
   → mixer / DSP / HAL
   → codec
   → microphone / speaker / Bluetooth / USB route

外设故障定位：

::

   user-visible failure
   → verify app request and permission
   → verify service ownership / route
   → verify driver and firmware state
   → verify hardware event / buffer
   → verify return callback and UI update

概念辨析
--------

* **Input latency 与 UI latency**：触摸事件可能已经及时到达系统，但 App 主线程晚处理仍会让用户感觉“触控慢”。
* **Audio stream 与 audio route**：stream 表示逻辑播放/录音，route 决定实际走哪个 microphone、speaker 或外接设备。
* **Display buffer 与 panel output**：App 交出 buffer 后仍要经过系统合成、VSync 和 scanout。
* **Camera module 与 Camera API**：硬件模组是物理设备组合，Camera API 是系统筛选后的能力表面。
* **Haptic request 与实际反馈**：系统可能根据设备能力、省电、设置和交互策略修改或忽略某些触觉请求。

本章结论
--------

手机外设不是 App 可以直接占有的独立设备，而是由系统服务统一管理的交互能力。分析显示、触摸、音频、相机和触觉问题时，应把硬件事件、driver、service、route/session、App callback 与用户可见时间线放在一起，才能找到真正的责任边界。