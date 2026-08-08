第156章：Trace Reading App to Service to Kernel to Hardware
============================================================

核心知识点
----------

* Trace 阅读的核心是把用户可见现象放回同一时间轴，并沿 ``App → Framework → IPC → System Service → Kernel / Driver → Hardware`` 追踪责任。
* 第一步永远是锁定症状窗口，例如 ``T_click → T_first_frame_present``、``T_play → T_audio_output``、``T_request → T_response``。窗口之外的热点只能作为背景，不能直接参与定责。
* Trace 必须区分“执行”和“等待”。线程 running 表示正在消耗 CPU；runnable 表示想运行但没拿到 CPU；blocked/sleeping 表示在等锁、IPC、I/O、timer、buffer、fence 或其它事件。
* 看到线程等待时，责任链不能停在等待者。应继续寻找等待对象的拥有者，例如 Binder 对端、持锁线程、driver queue、GPU fence 或网络对端。
* 常见 trace 对象包括 ``slice``、``instant event``、``counter``、``state track`` 与 ``thread scheduling``。它们分别回答阶段耗时、关键事件、资源数值、状态变化和线程调度。
* App event 到 Framework call 的第一段负责判断问题是否已经发生在 App 自己的主线程、UI 构建、同步初始化、decode、锁或调用前状态机中。
* Framework call 跨进程后，应主动寻找 Binder / XPC / daemon 边界，确认 transaction/reply、callback 和 timeout 的方向。
* System Service 层需要判断当前是在执行策略、等待资源、排队、进行权限/生命周期检查，还是已经把请求下发到 HAL/driver。
* Kernel / Driver / Hardware 层主要通过 sched、freq、IRQ、I/O、queue、counter、DMA、buffer、fence 等事实解释底层等待。硬件忙并不意味着根因一定在硬件，也可能是上层制造了过量请求。
* Trace 阅读要覆盖“请求”和“回程”。Camera、graphics、audio 等能力常在 callback、buffer、fence、present 的返回路径上产生主要延迟。
* Android Perfetto 更容易观察 Binder、sched、freq、FrameTimeline、ftrace 与系统服务；Apple Instruments 更稳定暴露 App thread、dispatch queue、signpost、Core Animation、Metal、network、energy 等公开轨迹。
* Apple 私有 daemon 内部细节不可作为稳定事实。应区分“公开 trace 直接观察”与“根据时间相关性作出的系统边界推断”。
* 最终结论应能回答三个问题：哪个阶段最先超时或变慢、线程当时是在执行还是等待、等待或资源所有者位于哪个责任层。

关键路径
--------

跨层 Trace 阅读：

::

   define user-visible interval
   → locate App event / main thread
   → inspect running vs runnable vs blocked
   → locate Framework call
   → locate IPC transaction / reply / callback
   → inspect System Service queue and policy
   → inspect kernel scheduling / I/O / freq
   → inspect driver queue / buffer / fence / hardware counter
   → follow return path to App-visible result
   → assign first delayed boundary

相机首帧示例：

::

   tap camera page
   → main thread calls camera framework
   → Binder / XPC request
   → camera service resource arbitration
   → HAL / driver config
   → sensor produces first buffer
   → callback / buffer queue
   → GPU / compositor
   → display present

概念辨析
--------

* **Running 与 Runnable**：running 表示线程正在 CPU 上执行，runnable 表示线程准备执行但在调度队列中等待 CPU。
* **Slice 与 Counter**：slice 表示某段工作持续时间，counter 表示随时间变化的资源数值；二者需要同窗关联。
* **Caller Slow 与 Callee Slow**：调用线程等待很久不代表调用方代码慢，可能是远端 service、driver 或资源迟迟未返回。
* **App Jank 与 GPU Jank**：用户只看到帧迟到；只有 trace 证明 App 提交已按时、GPU 或合成阶段最先超预算后，才能向下归因。
* **相关性与因果性**：温度升高、CPU 降频、queue 变长同时出现是线索；还需沿事件顺序证明哪一项先改变并影响目标路径。

本章结论
--------

Trace 的稳定阅读方法是 ``锁定症状窗口 → 找 App 起点 → 判断执行/等待 → 跨 IPC 追责任 → 检查系统服务 → 下钻 Kernel/Driver/Hardware → 沿回程确认用户结果``。任何跨层诊断都应找到“第一个明显偏离正常时间预算的边界”，再把后续现象视为结果而不是根因。