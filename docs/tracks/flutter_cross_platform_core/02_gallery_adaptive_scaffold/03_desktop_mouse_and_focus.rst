========================================================================================
第 3 节：桌面端鼠标光标调度 (MouseRegion)、轮播弹簧吸附与键盘焦点管理
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``cxyFork-gallery/lib/pages/home.dart`` 与 ``cxyFork-gallery/lib/pages/backdrop.dart``
   * **底层依赖源码**：``flutter-3.32.0/packages/flutter/lib/src/rendering/mouse_tracker.dart``、``packages/flutter/lib/src/widgets/focus_manager.dart`` 与 ``packages/flutter/lib/src/physics/spring_simulation.dart``
   * **核心使命**：以 macOS / Windows 桌面端人机交互规范为基准，深度解构触屏手势与桌面外设的交互断层、Flutter 引擎层 ``MouseTracker`` 悬停光标调度流水线、桌面轮播图 ``_SnappingScrollPhysics`` 弹簧吸附物理学，以及基于 ``FocusScope`` 与 ``KeyboardListener`` 的全键盘快捷键与无障碍隔离机制。

----------------------------------------------------------------------------------------

第一幕：鼠标外设物理特性与 `MouseTracker` 调度流水线
----------------------------------------------------

移动端触屏与桌面端鼠标存在本质的**输入物理模型差异**：
* **移动触屏（Touch Screen）**：输入是不连续的。只有手指接触屏幕瞬间才会产生 ``PointerDownEvent``，抬起后输入立即中断；
* **桌面鼠标（Mouse Device）**：输入是**连续且常驻的**。即使鼠标未按下任何按键，光标在屏幕上方移动时，操作系统仍在源源不断地向应用推送物理坐标悬停事件（Hover Event）。

1. `MouseTracker` 悬停候选收集与光标分发
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 Flutter 3.32 渲染层（``packages/flutter/lib/src/rendering/mouse_tracker.dart``）中，由 ``MouseTracker`` 单例统领全局鼠标交互：

.. code-block:: text

   [鼠标移动: 操作系统产生原始坐标]
                   │
                   ▼
   1. PlatformDispatcher 接收原始 PointerHoverEvent ──> 投递给 GestureBinding
                   │
                   ▼
   2. RendererBinding.mouseTracker 启动微观命中测试 (HitTest)
                   │
                   ▼
   3. 遍历渲染树，收集当前光标位置下所有的 MouseTrackerAnnotation 节点
                   │
                   ├── 比对上一帧命中列表 ──> 对移出节点触发 onExit
                   ├── 对新进入节点触发 onEnter
                   └── 对存留节点触发 onHover
                   │
                   ▼
   4. 提取顶层节点的 cursor 属性 (如 SystemMouseCursors.click)
                   │
                   ▼
   5. 回调宿主 C++ Embedder 修改操作系统原生光标样式 (macOS NSCursor / Windows IDC_HAND)

2. Gallery 业务组件的悬停光标注入
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 ``lib/pages/home.dart`` 中，所有卡片与外部链接均包裹了 ``MouseRegion``：
* 当鼠标移入时，光标由默认的标准箭头（``SystemMouseCursors.basic``）瞬时切换为交互小手指针（``SystemMouseCursors.click``）；
* 为桌面用户提供了最基础且必须的“可点击性（Affordance）”视觉心理暗示。

----------------------------------------------------------------------------------------

第二幕：桌面轮播图（`_DesktopCarousel`）与弹簧吸附物理学
--------------------------------------------------------

在手机上，用户习惯通过大拇指左右划动触摸屏来浏览轮播图（``PageView``）；但在桌面端，如果强迫用户按住鼠标左键横向拖拽几百像素，会造成极大的手腕疲劳与操作生硬感。

Gallery 在 ``lib/pages/home.dart`` 中实现了一套软硬兼顾的桌面专属轮播方案：

1. 左右悬浮翻页小圆钮 (`_DesktopPageButton`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 在轮播图两侧注入绝对定位的半透明翻页按钮（``_DesktopPageButton``）；
* **动态可见性判定**：
  * 当 ``ScrollController.offset > 0`` 时，显示左翻页按钮；
  * 当 ``ScrollController.offset < maxScrollExtent`` 时，显示右翻页按钮；
* **步长精确定位**：点击按钮时，执行 ``_controller.animateTo(_controller.offset ± _carouselItemWidth, duration: 200ms, curve: Curves.easeInOut)``，支持鼠标单次精准向前/向后推进一个完整卡片宽度（296px）。

2. 自定义弹簧吸附物理学 (`_SnappingScrollPhysics`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了让鼠标滚轮或触控板滑动后的停靠点永远对齐卡片边缘，代码重写了自定义滚动物理学 ``_SnappingScrollPhysics``：

* **吸附目标像素点方程 (`_getTargetPixels`)**：
  设单个卡片跨度为 $W_{	ext{item}}$，当前滚动偏移为 $P$，滑动释放瞬时速度为 $V$：
  $$	ext{TargetIndex} = \left\lfloor \frac{P}{W_{	ext{item}}} + \operatorname{sgn}(V) 	imes 0.5 \right\rceil$$
  $$	ext{TargetPixels} = \min(	ext{TargetIndex} 	imes W_{	ext{item}}, 	ext{maxScrollExtent})$$
* **弹簧阻尼运动方程 (`ScrollSpringSimulation`)**：
  当释放速度或惯性滑动使停靠位置发生微小偏差时，系统构造二次微分弹簧阻尼方程：
  $$F = -k(x - 	ext{TargetPixels}) - c \cdot v$$
  驱动列表在最后一公分产生细腻自然的物理回弹吸附（Snapping），确保视野中永远完整呈现整数张卡片。

----------------------------------------------------------------------------------------

第三幕：键盘焦点树、快捷键拦截与无障碍隔离
------------------------------------------

桌面专业用户高度依赖键盘（Tab / Shift+Tab / 回车 / ESC）完成无鼠标全键盘导航。

在 ``lib/pages/backdrop.dart`` 与 ``home.dart`` 中，构筑了严密的焦点树与语义隔离结构：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ Backdrop 根脚手架                                                         │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. KeyboardListener (系统快捷键拦截中枢)                                   │
   │    • 监听: onKeyEvent 捕捉 event.logicalKey == LogicalKeyboardKey.escape │
   │    • 动作: 瞬时触发 _toggleSettings() 关闭面板                            │
   │                                                                          │
   │ 2. FocusScope (焦点作用域隔离)                                            │
   │    • 状态开: 激活 FocusScope，Tab 键焦点被约束在设置面板内部循环          │
   │    • 状态关: 切换为 ExcludeFocus，彻底切断底层隐藏控件的 Tab 键可达性      │
   │                                                                          │
   │ 3. FocusTraversalGroup (有序遍历群组)                                     │
   │    • policy: WidgetOrderTraversalPolicy() 保证从上至下、从左至右导航       │
   └──────────────────────────────────────────────────────────────────────────┘

1. `KeyboardListener` 与 `Escape` 快捷键全局拦截
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 ``Backdrop._buildStack`` 中，当设置抽屉处于展开状态时，外层包裹 ``KeyboardListener``：
* 拦截键盘事件，当捕获到 ``LogicalKeyboardKey.escape`` 时，自动调用 ``_toggleSettings()`` 关闭面板；
* 符合 macOS / Windows 用户按下 ESC 键退出模态层的肌肉记忆。

2. `ExcludeFocus` 与 `ExcludeSemantics` 物理防线
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **焦点逃逸漏洞**：若直接隐藏设置面板（仅调整透明度或移出屏幕），盲人屏幕朗读器（VoiceOver / TalkBack）或 Tab 键仍可能意外选中屏幕外看不见的复选框或按钮；
* **工程防线**：
  * 面板关闭时，显式使用 ``ExcludeFocus(child: _settingsPage)``，将整个子树从焦点树（Focus Tree）中物理剪枝；
  * 同步包裹 ``ExcludeSemantics(excluding: !isSettingsOpen)``，将不可见节点从无障碍语义树中剔除，确保无障碍屏幕朗读器只朗读当前视口可见内容。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 02 第 3 节：``02_gallery_adaptive_scaffold/03_desktop_mouse_and_focus.rst`` 已全量落盘完工**！系统拆解了 MouseTracker 悬停光标流、_SnappingScrollPhysics 弹簧吸附方程、KeyboardListener 快捷键拦截与 FocusScope 隔离树。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 02 第 4 节：``02_gallery_adaptive_scaffold/04_splash_and_backdrop.rst``**。
  我们将深入 ``cxyFork-gallery/lib/pages/splash.dart`` 与 ``backdrop.dart`` 源码，系统剖析 ``SplashPage`` 自适应几何形变插值（``RelativeRectTween``）、``Peek Height`` 物理预留高度、以及 ``Backdrop`` 双层底板在移动端纵向滑动与桌面端锚点缩放卡片（``ScaleTransition``）的形态分化。
