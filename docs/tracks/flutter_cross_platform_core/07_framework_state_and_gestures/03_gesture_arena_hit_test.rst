========================================================================================
第 3 节：PointerEvent 物理事件流、HitTest 树状收集与手势竞技场仲裁机制
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``flutter-3.32.0/packages/flutter/lib/src/gestures/arena.dart``、``hit_test.dart``、``recognizer.dart`` 与 ``pointer_router.dart``
   * **底层依赖源码**：``packages/flutter/lib/src/gestures/binding.dart`` 与 ``packages/flutter/lib/src/rendering/box.dart``
   * **核心使命**：以操作系统电容屏硬件中断到像素级交互仲裁为基准，深度解构从原生触控包（``ui.PointerDataPacket``）到 Dart ``PointerEvent`` 的物理转换流水线、基于逆向深度优先遍历的 ``HitTestResult`` 坐标变换与命中测试收集、``PointerRouter`` 路由分发管道、以及 ``GestureArenaManager`` 基于主动抢占（Eager Winner）、逐级排他（Elimination）、抬手扫掠（Sweep）与延迟挂起（Hold/Release）的手势竞技场决胜算法。

----------------------------------------------------------------------------------------

第一幕：从硬件电容屏中断到 `PointerEvent` 物理流转
--------------------------------------------------

在智能手机与触控桌面设备上，用户的交互源于屏幕玻璃下方的电容感应矩阵：

1. **硬件层中断采样**：
   * 手指接触屏幕瞬间引发局部电容变化，触控 IC 芯片以 120Hz ~ 240Hz 采样率向操作系统内核发送硬件中断（IRQ）；
   * Linux / Android 驱动通过 ``/dev/input/event*``（``evdev`` 协议）上报原始坐标；iOS 驱动通过 IOKit 将事件投递给 ``UIKit``；macOS / Windows 捕获鼠标或触控板事件。
2. **C++ Embedder 引擎打包与二进制跨界投递**：
   * Flutter 原生 Embedder 捕获操作系统原生事件后，将其封装为扁平紧凑的二进制结构体：``ui.PointerDataPacket``；
   * Embedder 通过 Dart 原生调用（Dart C API）触发 ``PlatformDispatcher.instance.onPointerDataPacket``，将数据包零拷贝注入 UI 线程中的 Dart 虚拟机。
3. **`GestureBinding` 事件解包流水线**：
   * ``GestureBinding._handlePointerDataPacket`` 遍历数据包，将二进制数据转化为高阶领域事件：
     * ``PointerDownEvent``：手指初次接触屏幕（触发命中测试与竞技场创建）；
     * ``PointerMoveEvent``：手指在屏幕上发生位移（触发手势识别器阈值判定）；
     * ``PointerUpEvent``：手指离开屏幕（触发手势扫掠与默认决胜）；
     * ``PointerCancelEvent``：系统级弹窗或手势被打断（触发全局重置与资源清理）。

----------------------------------------------------------------------------------------

第二幕：命中测试（Hit Testing）的树状逆向递归遍历
--------------------------------------------------

当 ``PointerDownEvent`` 发生时，框架的首要任务是确定**屏幕上究竟有哪些组件处于该触摸点的物理几何包围盒之内**。

系统启动了自顶向下的命中测试遍历（Hit Testing）：

.. code-block:: text

   [PointerDownEvent: 物理屏幕全局坐标 (x, y)]
                         │
                         ▼
   1. GestureBinding.hitTestInView(result, position, viewId)
                         │
                         ▼
   2. RenderView.hitTest(result, position) ──► 从根节点向下递归
                         │
   ┌─────────────────────┴────────────────────────────────────────────────────┐
   │ RenderBox.hitTest 逆向深度优先遍历 (Child-First)                         │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 步骤 A: 局部坐标变换 (BoxHitTestResult.addWithPaintTransform)            │
   │        • 利用逆矩阵将父级屏幕绝对坐标转换为当前 RenderBox 的局部相对坐标  │
   │                                                                          │
   │ 步骤 B: 优先测试子节点 (hitTestChildren)                                  │
   │        • 按照 Z 轴层级从最上层的子节点向最下层的子节点逆序遍历 (Last to First)│
   │        • 一旦子节点命中了该点，子节点首先将自身压入 HitTestResult 路径栈 │
   │                                                                          │
   │ 步骤 C: 测试自身几何包围盒 (hitTestSelf)                                 │
   │        • 检查 position 是否落在当前 RenderBox 的 size (宽高) 矩形之内    │
   │                                                                          │
   │ 步骤 D: 压入命中结果集 (result.add(BoxHitTestEntry(this, transformedPos)))│
   └──────────────────────────────────────────────────────────────────────────┘

1. `HitTestBehavior` 的三种物理阻断策略
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 ``GestureDetector`` 与 ``Listener`` 中，``behavior`` 属性决定了命中测试在穿透空白区域时的行为：
* **`HitTestBehavior.deferToChild`（默认值）**：仅当子节点真正被命中时，自身才参与事件响应。如果点击了子组件之间的空白内边距，事件直接穿透至下层兄弟节点；
* **`HitTestBehavior.opaque`（不透明阻断）**：将当前组件的整个尺寸矩形视为物理不透明实体。即使点击了空白处，``hitTestSelf`` 亦强行返回 ``true``，阻止事件穿透到下层组件；
* **`HitTestBehavior.translucent`（半透明穿透）**：自身捕获事件，但允许命中测试继续向下穿透，使得上层组件与下层被遮挡的组件能够同时捕获该手势。

----------------------------------------------------------------------------------------

第三幕：手势竞技场（`GestureArenaManager`）决胜仲裁算法
--------------------------------------------------------

在一次点击或滑动中，多个手势识别器（如 ``TapGestureRecognizer``、``PanGestureRecognizer``、``LongPressGestureRecognizer``）可能同时位于 ``HitTestResult`` 路径上。

Flutter 并不依赖死板的父子优先级，而是建立了**手势竞技场（Gesture Arena）**，让所有竞争者在相同的物理时间轴上公平决胜：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ GestureArenaManager 状态机生命周期 (每个 pointer 拥有独立竞技场)          │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. 竞技场开启 (add):                                                      │
   │    • PointerDown 期间，所有命中的 Recognizer 调用 arena.add(pointer, this) │
   │    • 成员列表: members = [ TapRecognizer, PanRecognizer, LongPress... ]  │
   │    • 状态标记: isOpen = true                                             │
   │                                                                          │
   │ 2. 竞技场关闭 (close):                                                    │
   │    • PointerDown 分发完毕瞬间调用 arena.close(pointer)                    │
   │    • 状态标记: isOpen = false ──► 锁死大门，禁止新竞争者加入              │
   │                                                                          │
   │ 3. 决胜仲裁四种可能路径:                                                  │
   │    ├── 路径 A: 主动抢占胜利 (Eager Winner)                                │
   │    │          • 滑动位移突破 18px 阈值 ──► PanRecognizer 宣告 accepted     │
   │    │          • 立即将唯一胜利赋予该成员，其他所有成员全部收到 rejectGesture │
   │    │                                                                      │
   │    ├── 路径 B: 排他自退与唯一幸存者 (Elimination -> Sole Survivor)        │
   │    │          • 超出点击位移阈值 ──► TapRecognizer 宣告 rejected 退出     │
   │    │          • 剩余成员数 members.length == 1 ──► 唯一幸存者自动获胜     │
   │    │                                                                      │
   │    ├── 路径 C: 抬手扫掠强制决胜 (Sweep)                                   │
   │    │          • 用户抬起手指 (PointerUp) 且尚未分出胜负                   │
   │    │          • sweep() 触发: members.first (最深层子节点) 强制获胜      │
   │    │                                                                      │
   │    └── 路径 D: 延时保持 (Hold & Release)                                  │
   │               • DoubleTapRecognizer 判定可能存在二次点击 ──► 调用 hold()   │
   │               • 阻塞 sweep() 扫掠，等待 300ms 计时器归零后再 release()   │
   └──────────────────────────────────────────────────────────────────────────┘

1. 触控死区（Touch Slop）物理阈值
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了防止用户手指在屏幕上的微小生理颤抖（Jitter）被误判为拖拽手势，框架在 ``kTouchSlop`` 中定义了物理死区常量：
* 触屏设备标准死区为 **18.0 逻辑像素**（桌面精确鼠标为 **4.0 逻辑像素**）；
* 当手指位移处于 18.0px 之内时，``PanGestureRecognizer`` 保持观望，不发起决胜；
* 一旦欧氏距离 $\sqrt{\Delta x^2 + \Delta y^2} > 18.0	ext{px}$，``PanGestureRecognizer`` 立即调用 ``resolve(GestureDisposition.accepted)`` 宣告胜利，并瞬间击杀 ``TapGestureRecognizer``。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**【模块 07：状态分发与手势识别体系】全部 3 节已全量圆满完工并落盘**！
  深度解构了 ``InheritedElement`` 订阅哈希表与 $O(1)$ 局部更新、``ChangeNotifier`` 定长数组倍增与防重入深度追踪、以及 ``GestureArenaManager`` 手势竞技场四大决胜路径。
* **里程碑达成**：
  至此，**【第二部】向下穿透——Flutter 3.32 SDK 框架层核心机制（模块 05 ~ 07，共 10 篇源码级深度专著）已全部 100% 完工落盘**！
* **给下一个周期的施工建议**：
  下一个周期将正式跨入 **【第三部：底层基石——渲染管线、C++ 引擎与图形光栅化】**！
  我们将正式启动 **模块 08：帧生命周期与 VSync 硬件对齐** 的第一节：
  ``08_engine_frame_pipeline/01_embedder_and_threads.rst``。
  我们将深入 Flutter C++ 引擎源码（``shell/common/engine.cc`` 与 ``runtime/dart_vm.cc``），系统剖析 C++ Embedder 宿主工程架构、Platform / UI / Raster / IO 四大多线程并发模型与 TaskRunner 消息队列分发机制。
