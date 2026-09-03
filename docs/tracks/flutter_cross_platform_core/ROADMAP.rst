========================================================================================
全书施工路线图与进度追踪 (Roadmap & Architecture Blueprint)
========================================================================================

本项目作为自描述状态机，记录全书 9 大核心模块、32 个长篇深度源码剖析章节的规划与完成情况。

.. note::
   **状态机运行规则 (State Machine Execution Rules)**
   * **[x] 已完工**：代表该章节已完成深度打磨并成功落盘到目标模块目录；
   * **[ ] 待施工**：后台定时调度任务将按序自动锁定第一个 `[ ]` 章节进行撰写与落盘；
   * **自动翻转**：每次定时任务完成落盘后，会自动将对应章节标记从 `[ ]` 翻转为 `[x]`，并挂载到对应模块的 `index.rst`。

----------------------------------------------------------------------------------------

【第一部】Gallery 企业级全平台商业工程实战篇 (Modules 01 ~ 04，已全量 100% 完工)
==================================================================================

模块 01：Gallery 应用启动与全局架构基建 (Foundation & Architecture，已完工)
---------------------------------------------------------------------------
* [x] `01_gallery_foundation/01_main_bootstrap.rst` - main.dart 启动时序、字体锁死与本地持久化预热
* [x] `01_gallery_foundation/02_model_binding.rst` - gallery_options.dart 不可变配置载体与 ModelBinding 状态分发
* [x] `01_gallery_foundation/03_theme_and_tokens.rst` - gallery_theme_data.dart 语义化配色板与字体排版规范

模块 02：多端自适应布局与顶层脚手架架构 (Adaptive UI & Scaffold，已完工)
-------------------------------------------------------------------------
* [x] `02_gallery_adaptive_scaffold/01_adaptive_breakpoints.rst` - adaptive.dart 物理断点系统与小屏/大屏视图分流
* [x] `02_gallery_adaptive_scaffold/02_foldable_and_two_pane.rst` - 折叠屏物理铰链 (Hinge) 边界检测与 TwoPane 避让
* [x] `02_gallery_adaptive_scaffold/03_desktop_mouse_and_focus.rst` - 桌面端鼠标悬停 (MouseRegion)、左右翻页按钮与焦点管理
* [x] `02_gallery_adaptive_scaffold/04_splash_and_backdrop.rst` - splash.dart 启动过渡动效与 backdrop.dart 双层抽屉底板

模块 03：Gallery 5 大商业级 Study 源码深度剖析 (Studies Deep Dive，已完工)
--------------------------------------------------------------------------
* [x] `03_gallery_studies_deep_dive/01_rally_finance_charts.rst` - Rally 金融系统：Canvas 自绘贝塞尔曲线折线图与环形渐变饼图
* [x] `03_gallery_studies_deep_dive/02_shrine_asymmetric_layout.rst` - Shrine 电商系统：2+1 非对称交错商品流、切角边框与弹簧物理抽屉
* [x] `03_gallery_studies_deep_dive/03_reply_motion_and_notches.rst` - Reply 邮件系统：Material 3 容器流体变换与瀑布流几何缺口算法
* [x] `03_gallery_studies_deep_dive/04_crane_adaptive_forms.rst` - Crane 旅游系统：梯形 Tab 绘制器与多维折叠筛选表单
* [x] `03_gallery_studies_deep_dive/05_fortnightly_masonry_grid.rst` - Fortnightly 新闻系统：桌面端多列报纸瀑布流与字号自适应阶梯缩放

模块 04：声明式路由与 CodeViewer 语法引擎 (Routes & CodeViewer Engine，已完工)
-------------------------------------------------------------------------------
* [x] `04_gallery_routes_and_codeviewer/01_regex_routes_and_deferred.rst` - routes.dart 正则路径匹配与 deferred as 编译分包
* [x] `04_gallery_routes_and_codeviewer/02_codeviewer_ast_engine.rst` - CodeViewer 源码查看器引擎：AST 词法分词高亮与双视图联动

【第二部】向下穿透——Flutter 3.32 SDK 框架层核心机制 (Modules 05 ~ 07，已全量 100% 完工)
========================================================================================

模块 05：响应式核心——三棵树拓扑与 Diff 算法 (Three Trees & Diff Algorithm，已完工)
-----------------------------------------------------------------------------------
* [x] `05_framework_three_trees/01_widget_immutable_tree.rst` - Widget 不可变图纸与类型系统
* [x] `05_framework_three_trees/02_element_lifecycle_and_mount.rst` - Element 树的生命周期、挂载 (mount)、复用与卸载
* [x] `05_framework_three_trees/03_diff_algorithm_and_keys.rst` - updateChild 两级 Diff 算法与 Key 跨父级重挂载原理
* [x] `05_framework_three_trees/04_build_owner_dirty_scope.rst` - BuildOwner 调度中枢、BuildScope 深度排序与 Dirty 元素批量重构

模块 06：布局系统与几何约束求解 (Layout System & Constraints，已完工)
---------------------------------------------------------------------
* [x] `06_framework_layout_system/01_box_constraints_protocol.rst` - BoxConstraints 盒约束传递法则 (向下传约束，向上报尺寸)
* [x] `06_framework_layout_system/02_render_box_layout_flow.rst` - RenderBox.performLayout 测量与 parentData 坐标计算
* [x] `06_framework_layout_system/03_relayout_boundary.rst` - Relayout Boundary (重新布局边界) 性能隔离机制
* [x] `06_framework_layout_system/04_sliver_scroll_viewport.rst` - Sliver 滚动流式布局、Viewport 视口与懒加载机制
* [x] `06_framework_layout_system/05_render_flex_algorithm.rst` - RenderFlex 弹性排版与剩余空间分配算法

模块 07：状态分发与手势识别体系 (State & Gestures，已完工)
----------------------------------------------------------─
* [x] `07_framework_state_and_gestures/01_inherited_element_hash_table.rst` - InheritedElement 订阅哈希表与 $O(1)$ 精准局部重绘
* [x] `07_framework_state_and_gestures/02_listenable_and_changenotifier.rst` - ValueNotifier 与 ChangeNotifier 观察者模式
* [x] `07_framework_state_and_gestures/03_gesture_arena_hit_test.rst` - PointerEvent 物理事件、HitTest 树状收集与手势竞技场仲裁

【第三部】底层基石——渲染管线、C++ 引擎与图形光栅化 (Modules 08 ~ 09，已全量 100% 完工)
========================================================================================

模块 08：帧生命周期与 VSync 硬件对齐 (Frame Pipeline & VSync，已完工)
----------------------------------------------------------------------
* [x] `08_engine_frame_pipeline/01_embedder_and_threads.rst` - C++ Embedder 宿主工程与 Platform/UI/Raster 三大线程
* [x] `08_engine_frame_pipeline/02_platform_dispatcher_pipeline.rst` - PlatformDispatcher 原生事件管道与 Multi-View 视口管理
* [x] `08_engine_frame_pipeline/03_widgets_flutter_binding_mixins.rst` - WidgetsFlutterBinding 七大底层 Mixin 初始化拓扑
* [x] `08_engine_frame_pipeline/04_scheduler_vsync_phases.rst` - 硬件 VSync 信号驱动与 SchedulerBinding 四大帧阶段

模块 09：图层合成与 GPU 光栅化 (Rendering & GPU Pipeline，已完工)
------------------------------------------------------------------
* [x] `09_engine_rendering_and_gpu/01_pipeline_owner_flush.rst` - PipelineOwner 刷新五大阶段 (flushLayout/flushPaint)
* [x] `09_engine_rendering_and_gpu/02_repaint_boundary_and_layers.rst` - Repaint Boundary (重绘边界) 与图层树 (LayerTree) 合成
* [x] `09_engine_rendering_and_gpu/03_scene_builder_and_gpu_raster.rst` - SceneBuilder 场景打包与 Skia/Impeller GPU 光栅化提交
* [x] `09_engine_rendering_and_gpu/04_platform_channels_binary_messenger.rst` - BinaryMessenger 二进制内存共享与跨语言零拷贝通信
