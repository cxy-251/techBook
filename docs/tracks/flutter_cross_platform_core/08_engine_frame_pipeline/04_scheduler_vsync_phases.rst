========================================================================================
第 4 节：SchedulerBinding 五阶段单帧状态机、Ticker 动画步进与 VSync 硬件对齐
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **底层 Framework 源码**：``flutter-3.32.0/packages/flutter/lib/src/scheduler/binding.dart``、``ticker.dart`` 与 ``priority.dart``
   * **核心使命**：以现代实时图形渲染管线与硬件时钟同步为基准，深度解构 Flutter 帧调度中枢 ``SchedulerBinding`` 的五阶段单帧驱动状态机（``idle`` $	o$ ``transientCallbacks`` $	o$ ``midFrameMicrotasks`` $	o$ ``persistentCallbacks`` $	o$ ``postFrameCallbacks``）、动画 ``Ticker`` 基于单调递增时间基准（``currentFrameTimeStamp``）的物理步进数学方程、``timeDilation`` 时间膨胀与 ``resetEpoch`` 防回退机制、以及基于二叉堆优先级队列（``HeapPriorityQueue``）的帧间空闲算力调度策略。

----------------------------------------------------------------------------------------

第一幕：五阶段单帧驱动状态机（`SchedulerPhase`）与 VSync 物理时序
------------------------------------------------------------------

在声明式 UI 体系中，界面的更新绝不是杂乱无章的即时重绘，而是被操作系统显示器的垂直同步信号（VSync，60Hz 时每 16.6ms 一次，120Hz 时每 8.3ms 一次）严格节奏化约束的。

``SchedulerBinding`` 将每一帧的生命周期划分为 5 个具有严格偏序关系的执行阶段（``SchedulerPhase``）：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ SchedulerBinding 单帧驱动五阶段状态机流水线                              │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. idle (空闲态):                                                        │
   │    • 当前无活动帧，CPU 执行普通的 Microtask、Timer 与底层网络 I/O 回调    │
   │    • 运行低优先级空闲任务 (HeapPriorityQueue 调度)                       │
   │                                                                          │
   │ 2. transientCallbacks (瞬态动画回调阶段):                                 │
   │    • 由 PlatformDispatcher.onBeginFrame(rawTimeStamp) 硬件脉冲唤醒       │
   │    • 执行所有 Ticker 与 AnimationController，推进动画至当前物理时间点     │
   │                                                                          │
   │ 3. midFrameMicrotasks (帧中微任务清理阶段):                               │
   │    • 自动清空由 transientCallbacks 触发生成的所有微任务队列 (Futures)    │
   │                                                                          │
   │ 4. persistentCallbacks (持久化构建/排版/绘制阶段):                       │
   │    • 由 PlatformDispatcher.onDrawFrame() 触发                             │
   │    • 驱动 WidgetsBinding.drawFrame ──► BuildOwner ──► PipelineOwner 刷新  │
   │                                                                          │
   │ 5. postFrameCallbacks (帧后清理与测量阶段):                               │
   │    • 帧主干渲染已完全提交，执行 addPostFrameCallback 注册的一次性回调     │
   │    • 适用于安全读取 RenderBox 物理尺寸、弹出全局弹窗与帧耗时监控          │
   │    • 退出后状态机重新归位至 idle                                         │
   └──────────────────────────────────────────────────────────────────────────┘

1. `handleBeginFrame` 与时间戳单调归一化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当硬件 VSync 脉冲到来时，C++ 引擎触发 ``PlatformDispatcher.onBeginFrame``：
* 传入原生硬件时间戳 ``rawTimeStamp``；
* 调度器调用 ``_adjustForEpoch()`` 将其转换为以应用启动为原点的**绝对单调递增时间戳（``currentFrameTimeStamp``）**；
* 状态机切入 ``SchedulerPhase.transientCallbacks``，遍历执行所有已注册的 ``_transientCallbacks`` 字典，将各动画控制器推进到当前时间点。

2. `handleDrawFrame` 与流水线闭环
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
紧随其后，C++ 引擎触发 ``PlatformDispatcher.onDrawFrame``：
* 状态机切入 ``SchedulerPhase.persistentCallbacks``，执行唯一的永久回调：``WidgetsBinding.drawFrame()``；
* 依次驱动组件树构建、RenderObject 布局计算与 LayerTree 图层合成；
* 完成后切入 ``SchedulerPhase.postFrameCallbacks``，清空 ``_postFrameCallbacks`` 列表并完成整帧时序归档。

----------------------------------------------------------------------------------------

第二幕：动画 `Ticker` 步进数学原理与时间膨胀（`timeDilation`）
---------------------------------------------------------------

在 ``flutter-3.32.0/packages/flutter/lib/src/scheduler/ticker.dart`` 中，``Ticker`` 充当了动画的物理起搏器：

1. `Ticker` 驱动方程与物理插值
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当 ``AnimationController.forward()`` 启动时，它通过 ``createTicker`` 向调度器注册帧回调：
* 记录动画启动时的基准时间戳 $T_{	ext{start}}$；
* 在随后的每一个 VSync 帧中，接收调度器传入的当前帧时间戳 $T_{	ext{now}}$；
* **物理时间跨度增量方程**：
  $$\Delta t = T_{	ext{now}} - T_{	ext{start}}$$
* **动画归一化进度因子**：
  $$t_{	ext{progress}} = \operatorname{clamp}\left(\frac{\Delta t}{	ext{Duration}}, 0.0, 1.0\right)$$
* 进度因子输入给指定的缓动曲线（``Curve.transform(t)``），输出最终的插值属性并标记元素为 Dirty。

2. `timeDilation` 与 `resetEpoch` 防回退机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在性能调试（如 DevTools 开启 5x 慢动作）时，系统通过修改全局变量 ``timeDilation``：
* 若直接在运行时突变缩放因子，会导致计算出的 $\Delta t$ 出现瞬间跳跃甚至负增长（时间倒流错误）；
* ``SchedulerBinding.resetEpoch()`` 在修改膨胀因子的瞬间，将当前物理时间作为新的纪元基准（Epoch Start），使输出的时间戳曲线呈现**严格单调连续平滑**，彻底消除了慢动作调试时的动画跳跃。

----------------------------------------------------------------------------------------

第三幕：二叉堆优先级任务队列（`HeapPriorityQueue`）与空闲算力榨取
------------------------------------------------------------------

除了每帧的强制渲染外，应用经常需要执行一些耗时但不紧急的后台工作（如预热图片缓存、计算搜索索引）。

``SchedulerBinding`` 引入了基于二叉堆（``HeapPriorityQueue``）的优先级任务调度器（``scheduleTask``）：

.. code-block:: text

   Priority 任务优先级矩阵 (从高到低排序)
        │
        ├── Priority.kMaxPriority (100000) ── 紧急硬件中断响应
        ├── Priority.touch        (2000)   ── 正在处理用户触摸交互
        ├── Priority.animation    (100)    ── 动画运行阈值线 (Below this are paused)
        ├── Priority.idle         (0)      ── 帧间空闲时段运行
        └── Priority.kMinPriority (-10000) ── 极低优先级后台垃圾整理

1. `defaultSchedulingStrategy` 动态策略裁决
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 当屏幕上正有动画处于活跃运行状态时（``transientCallbackCount > 0``）；
* 调度策略自动生效：**强制挂起所有优先级低于 `Priority.animation` 的非紧急任务**；
* 确保 CPU 算力 100% 优先供给动画和排版流水线，彻底杜绝后台运算导致的丢帧掉帧。
* 当动画结束、状态机回归 ``idle`` 阶段时，调度器通过 ``Timer.run`` 从堆顶依次弹出最高优先级的任务执行。

----------------------------------------------------------------------------------------

第四幕：`scheduleWarmUpFrame` 首帧跳过 VSync 加速与 `addPostFrameCallback`
--------------------------------------------------------------------------

1. `scheduleWarmUpFrame()` 冷启动黑科技
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在应用启动（``runApp``）或热重载（Hot Reload）时：
* 常规的 ``scheduleFrame()`` 需要等待下一次硬件 VSync 脉冲（可能需要等待 10~15ms）；
* ``scheduleWarmUpFrame()`` 强行在当前的微任务队列中**同步连续触发 `handleBeginFrame(null)` 与 `handleDrawFrame()`**；
* 在屏幕硬件发出刷新请求前，首帧的场景图层已经提前绘制完成并存入 GPU 缓冲区待命，实现了极限的冷启动响应速度。

2. `addPostFrameCallback` 宏任务实战价值
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 在 Widget 的 ``build()`` 执行期间，禁止直接修改状态（不允许在 build 里调用 ``setState``），且此时 ``RenderBox`` 尚未完成物理测量，无法获取准确的像素宽高；
* ``addPostFrameCallback`` 将逻辑推迟至当前帧完全绘制完毕的瞬间执行，是安全获取组件真实渲染尺寸（``context.size``）、触发页面转场弹窗、以及向性能分析工具上报帧耗时（``FrameTiming``）的标准入口。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**【模块 08：帧生命周期与 VSync 硬件对齐】全部 4 节已全量圆满完工并落盘**！
  系统彻底拆解了 Embedder 三大线程模型、PlatformDispatcher 原生事件管道、WidgetsFlutterBinding 七大 Mixin 拓扑、以及 SchedulerBinding 五阶段单帧状态机与 Ticker 物理步进。
* **给下一个周期的施工建议**：
  下一个周期将正式跨入 **【模块 09：图层合成与 GPU 光栅化】**！
  我们将深入推进第 1 节：``09_engine_rendering_and_gpu/01_pipeline_owner_flush.rst``。
  我们将深入 ``flutter-3.32.0/packages/flutter/lib/src/rendering/object.dart`` 源码，系统剖析核心渲染宿主 ``PipelineOwner`` 的五大阶段流水线（``flushLayout`` $	o$ ``flushCompositingBits`` $	o$ ``flushPaint`` $	o$ ``flushSemantics`` $	o$ ``flushInlinePredictions``），以及 Dirty 节点的拓扑排序与重绘重排隔离机制。
