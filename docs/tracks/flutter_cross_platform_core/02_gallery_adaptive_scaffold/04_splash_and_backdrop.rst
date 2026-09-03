========================================================================================
第 4 节：splash.dart 启动动效动力学插值与 backdrop.dart 双层底板架构深度解构
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``cxyFork-gallery/lib/pages/splash.dart`` 与 ``cxyFork-gallery/lib/pages/backdrop.dart``
   * **底层依赖源码**：``flutter-3.32.0/packages/flutter/lib/src/widgets/transitions.dart``、``packages/flutter/lib/src/widgets/layout_builder.dart`` 与 ``packages/flutter/lib/src/rendering/stack.dart``
   * **核心使命**：以多端全屏脚手架与转场动力学为基准，深度解构 ``SplashPage`` 基于 ``RelativeRectTween`` 的自适应几何形变插值、露出高度（Peek Height）物理预留、以及 ``Backdrop`` 双层底板在移动端纵向双轨滑动与桌面端右上角锚点非线性缩放（``ScaleTransition`` + ``Curves.fastOutSlowIn``）的形态分化。

----------------------------------------------------------------------------------------

第一幕：`SplashPage` 启动过渡状态机与几何动力学插值
---------------------------------------------------

在应用冷启动完成后，首屏呈现的并非静态死板的主页，而是通过 ``SplashPage`` 建立了一套**具有物理交互性与自适应形变**的过渡层：

1. 单时钟驱动与动态特效周期
~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **时钟信号（`SingleTickerProviderStateMixin`）**：
  驱动受全局生命周期约束的 ``AnimationController``，持续时间由常量 ``splashPageAnimationDuration`` 严格锁定；
* **特效字典与随机种子**：
  内部维护特效编号与时长的哈希映射（``_effectDurations``，时长介于 3~6 秒），冷启动时通过伪随机数发生器提取 ``_effect``，在后台渲染对应的品牌视觉资产。

2. `RelativeRectTween` 自适应几何动力学方程
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
前层主视图（Front Layer）在 Y 轴方向的位移距离，并非固定硬编码数值，而是通过 ``LayoutBuilder`` 动态读取当前宿主视口的物理约束边界后实时求解：

.. code-block:: text

   Animation<RelativeRect> _getPanelAnimation(BuildContext context, BoxConstraints constraints) {
     final height = constraints.biggest.height -
         (isDisplayDesktop(context) ? homePeekDesktop : homePeekMobile);
     return RelativeRectTween(
       begin: const RelativeRect.fromLTRB(0, 0, 0, 0),
       end: RelativeRect.fromLTRB(0, height, 0, 0),
     ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut));
   }

* **露出高度（Peek Height）物理规范**：
  * **移动端（``homePeekMobile = 60.0``）**：在屏幕底部仅保留 60 像素的微小露出高度，最大化展示后台启动动画；
  * **桌面端（``homePeekDesktop = 210.0``）**：在底部保留 210 像素的开阔视野，露出主页核心分类卡片的顶部预览；
* **物理位移边界计算**：
  $$	ext{SlideHeight} = H_{	ext{viewport}} - 	ext{PeekHeight}$$
  通过 ``RelativeRectTween`` 将矩形坐标从 $(0, 0, 0, 0)$ 线性插值到 $(0, 	ext{SlideHeight}, 0, 0)$，配合 ``Curves.easeInOut`` 缓动曲线，实现前层主视图如幕布般平滑下沉露出背景。

3. 手势动力学与通知解耦
~~~~~~~~~~~~~~~~~~~~~~~
* **快速上滑手势拦截**：
  前层视图包裹 ``GestureDetector``，在 ``onVerticalDragEnd`` 中监听瞬时速度向量，当向上滑动速度 $V_y < -200	ext{px/s}$ 时，触发 ``_controller.reverse()`` 瞬间收起幕布；
* **事件解耦（`ToggleSplashNotification`）**：
  深层子组件无需持有 ``_SplashPageState`` 的实例指针，直接调用 ``ToggleSplashNotification().dispatch(context)``，利用 Flutter 事件冒泡树将展开通知向上传递，实现了视图层级的零耦合。

----------------------------------------------------------------------------------------

第二幕：`Backdrop` 双层底板架构与多端形态分化
----------------------------------------------

Material Design 提出的双层底板（Backdrop）架构，由“前台主内容层（HomePage）”与“后台全局配置层（SettingsPage）”层叠组合而成。Gallery 针对移动端触屏与桌面端宽屏实现了两种截然不同的物理展开形式：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ Backdrop 顶层调度中枢                                                     │
   ├──────────────────────────────────────────┬───────────────────────────────┤
   │ 移动端分支形态 (Mobile Branch)            │ 桌面端分支形态 (Desktop Branch)│
   ├──────────────────────────────────────────┼───────────────────────────────┤
   │ • 纵向双轨对向滑动 (PositionedTransition)│ • 主页内容保持静止             │
   │ • 设置面板从屏幕顶部外方滑入             │ • 设置面板重构为右上角悬浮卡片 │
   │ • 主页内容同步向下滑出保留 Header        │ • ScaleTransition 锚点缩放弹出 │
   │ • 最大化利用纵向单列视口                 │ • ModalBarrier 阻挡层点击外部闭合│
   └──────────────────────────────────────────┴───────────────────────────────┘

1. 局部状态隔离防线 (`ValueNotifier<bool>`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **全局 Rebuild 性能危机**：设置面板的开闭属于高频局部交互。如果直接在 ``_BackdropState`` 中调用 ``setState()``，会导致底层的 ``HomePage`` 以及内部成百上千个展示卡片全部触发无谓的 ``build()``；
* **工程解法**：
  使用 ``ValueNotifier<bool> _isSettingsOpenNotifier`` 配合 ``ValueListenableBuilder``：
  * 面板开闭时，仅改变 ``_isSettingsOpenNotifier.value``；
  * 只有监听该变量的动画转场节点触发重绘，中间庞大的主页组件树完全保持静默。

2. 移动端：双轨纵向滑动算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **设置面板动画（`_slideDownSettingsPageAnimation`）**：
  起始坐标位于屏幕顶部外方（``RelativeRect.fromLTRB(0, -maxHeight, 0, 0)``），终止坐标为平铺全屏（``RelativeRect.fromLTRB(0, 0, 0, 0)``）；
* **主页滑出动画（`_slideDownHomePageAnimation`）**：
  起始坐标为全屏，终止坐标下沉至屏幕底部下方，仅保留顶部导航栏高度（``RelativeRect.fromLTRB(0, maxHeight - headerHeight, 0, -headerHeight)``）；
* **动画区间压缩（`Interval(0.0, 0.4, curve: Curves.ease)`）**：
  将整个面板的位移动作压缩在动画控制器的前 40% 时间窗口内完成，给用户呈现出极其干脆利落的响应手感。

3. 桌面端：右上角锚点非线性缩放卡片
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **布局重构**：主页内容在底层完全静止，设置面板被包装为一个带高程阴影（``Elevation: 7``）、圆角剪裁（``BorderRadius.circular(40)``）的高级浮动卡片（``constraints: maxWidth = 300px, maxHeight = 560px``）；
* **非线性缩放动力学（`ScaleTransition`）**：
  * 缩放原点（Alignment）根据当前文字排版方向动态对齐：LTR 语系对齐右上角（``Alignment.topRight``），RTL 语系对齐左上角（``Alignment.topLeft``）；
  * 缓动曲线采用 Material 经典的 ``Curves.fastOutSlowIn``（先急加速再缓慢停靠），模拟物理卡片从图标处瞬间弹出的张力感；
* **模态阻挡层（`ModalBarrier`）**：
  展开时在卡片后方注入透明的 ``ModalBarrier`` 并绑定 ``Listener(onPointerDown: (_) => _toggleSettings())``，用户点击桌面任何空白区域即可顺畅收回面板。

----------------------------------------------------------------------------------------

第三幕：系统级 UI 叠加样式与无障碍播报 (`AnnotatedRegion` & `SemanticsService`)
----------------------------------------------------------------------------------

1. 状态栏色彩自动反转 (`AnnotatedRegion`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 ``Backdrop`` 最外层包裹 ``AnnotatedRegion<SystemUiOverlayStyle>``：
* 动态调用 ``GalleryOptions.of(context).resolvedSystemUiOverlayStyle()``；
* 在浅色模式下将手机系统状态栏（电量、时间图标）自动切换为黑色图标（``SystemUiOverlayStyle.dark``），在深色模式下自动切换为白色图标（``SystemUiOverlayStyle.light``），确保系统顶栏与应用背景色永远维持高对比度。

2. 语音播报与无障碍辅助 (`SemanticsService`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当用户点击设置按钮触发开闭时：
* 触发 ``SemanticsService.announce(label, textDirection)``，主动向操作系统底层的无障碍服务通道（VoiceOver / TalkBack）推送多语言状态变更语音提示（如“设置已打开”或“设置已关闭”），实现世界一流的无障碍合规性。

----------------------------------------------------------------------------------------

小结与给下一个周期的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**【模块 02：多端自适应布局与顶层脚手架架构】全部 4 节已全量深度完工并落盘**！系统拆解了自适应断点系统、折叠双屏 Hinge 避让、桌面鼠标键盘焦点树、以及 Splash 与 Backdrop 双层底板的多端动力学架构。
* **给下一个周期的施工建议**：
  下一个周期将正式迈入 **【模块 03：Gallery 5 大商业级 Study 源码深度剖析】** 的首篇攻坚：
  ``03_gallery_studies_deep_dive/01_rally_finance_charts.rst``。
  我们将深入 ``cxyFork-gallery/lib/studies/rally/`` 源码，从零解构其基于 ``CustomPainter`` 的二次贝塞尔曲线平滑折线图（``line_chart.dart``）、带 $1^\circ$ 物理间隙的环形扫掠渐变饼图（``pie_chart.dart``）、零 Widget 开销的 ``TextPainter`` 画布文字排版、以及多 Tab 资产结算状态机（``finance.dart``）。
