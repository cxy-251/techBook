========================================================================================
第 1 节：routes.dart 正则路径匹配、声明式路由分发与 Web 异步分包状态机
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``cxyFork-gallery/lib/routes.dart`` 与 ``cxyFork-gallery/lib/deferred_widget.dart``
   * **底层依赖源码**：``flutter-3.32.0/packages/flutter/lib/src/widgets/navigator.dart`` 与 ``packages/flutter/lib/src/widgets/overlay.dart``
   * **核心使命**：以跨端 URL 寻址规范与现代 Web 编译分包物理学为基准，深度解构 Gallery 声明式路由引擎 ``RouteConfiguration.onGenerateRoute`` 的正则表达式捕获组动态提取、基于平台形态的路由容器分流（Web 无动画 / 折叠屏 TwoPane / 移动端标准滑动）、Dart 编译器 ``deferred as`` 延迟加载指令物理机制、以及 ``DeferredWidget`` 具备静态记忆化缓存（Memoization）的异步加载状态机。

----------------------------------------------------------------------------------------

第一幕：声明式 URL 路由分派与正则表达式引擎 (`RouteConfiguration`)
-------------------------------------------------------------------

在跨端（尤其是 Web 与桌面端）应用架构中，传统的命令式导航（如直接调用 ``Navigator.push(context, MaterialPageRoute(...))``）存在致命缺陷：
1. **URL 地址栏与视图割裂**：用户在浏览器中无法通过输入直达链接（Deep Link，如 ``https://app.com/demo/material-button``）直接进入目标页面；
2. **前进/后退历史栈不可控**：无法与浏览器的 History API 原生对齐；
3. **参数硬编码耦合**：目标页面的构造参数被散落在各个点击事件中，缺乏全局的路由寻址调度表。

在 ``lib/routes.dart`` 中，系统建立了一套基于**正则表达式模式匹配（RegExp Pattern Matching）**的声明式路由拓扑：

.. code-block:: text

   [用户请求路由路径: settings.name = '/demo/reply']
                           │
                           ▼
   1. 遍历 RouteConfiguration.paths 列表
                           │
                           ▼ 逐项执行 RegExp(path.pattern).hasMatch(settings.name)
   2. 命中规则: r'^/demo/([\w-]+)$'
                           │
                           ▼ 提取捕获组 Group(1)
   3. 提取动态 Slug 参数: match = 'reply'
                           │
                           ▼
   4. 执行 Path.builder(context, match) ──► 动态构造 DemoPage(slug: 'reply')
                           │
                           ▼
   5. 依据硬件与平台环境分发特定的 PageRoute 容器

1. 正则捕获组动态参数注入
~~~~~~~~~~~~~~~~~~~~~~~~~
在 ``Path`` 定义中，``builder`` 被声明为通用高阶函数：
$$	ext{typedef PathWidgetBuilder} = 	ext{Widget Function}(	ext{BuildContext}, 	ext{String}?)$$
* 当 URL 路径包含动态参数时（如组件唯一标识符 ``slug``），正则表达式 ``r'^' + DemoPage.baseRoute + r'/([\w-]+)$'`` 自动截获子串；
* 系统通过 ``firstMatch.group(1)`` 提取参数，直接注入目标页面的构造函数，实现了完全解耦的动态页面实例化。

2. 平台差异化路由容器的三大物理分支
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **Web 端分支（``NoAnimationMaterialPageRoute``）**：
  * 重写 ``buildTransitions`` 方法，直接返回未包裹动画的 ``child`` 页面；
  * 彻底消除 300 毫秒的移动端滑入动画，符合桌面网页链接即时呈现的交互预期。
* **折叠双屏分支（``TwoPanePageRoute``）**：
  * 继承自底层 ``OverlayRoute``，重写 ``createOverlayEntries()``；
  * 提取硬件铰链右侧坐标（``left: hinge.right``），生成仅覆盖屏幕右半区的局部 ``Positioned`` 遮罩层，保持左屏主页完全可见。
* **移动原生端分支（``MaterialPageRoute``）**：
  * 默认启用平台原生的转场动画（Android 自下而上淡入，iOS 自右向左横滑与边缘侧滑返回）。

----------------------------------------------------------------------------------------

第二幕：Dart 编译期代码分割（`deferred as`）的物理机制
------------------------------------------------------

大型多模块工程（如包含记账、电商、邮件等 5 大子系统的 Gallery）如果采用单一巨石打包（Monolithic Bundle）：
* Web 端的 ``main.dart.js`` / Wasm 产物体积将膨胀至几十兆；
* 浏览器在初次加载时，必须先将整个巨大的 JavaScript 文件完整下载并通过 V8 引擎解析编译，导致首屏可交互时间（TTI, Time to Interactive）高达数秒甚至几十秒。

1. `deferred as` 编译器物理切分
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 ``lib/routes.dart`` 头部，子系统模块被标记为延迟加载：

.. code-block:: text

   import 'package:gallery/studies/rally/app.dart' deferred as rally;
   import 'package:gallery/studies/shrine/app.dart' deferred as shrine;
   import 'package:gallery/studies/crane/app.dart' deferred as crane;

* **Dart 编译器动作**：
  * 编译器切断主入口对该子模块的静态依赖树链接；
  * 将 ``rally`` 及其专有资产单独编译为一个独立的动态代码分片（如 ``rally.part.js``）；
  * 自动在运行时命名空间中生成异步加载函数：``Future<void> rally.loadLibrary()``。

----------------------------------------------------------------------------------------

第三幕：`DeferredWidget` 记忆化状态机与零延迟二次加载
----------------------------------------------------

在 ``lib/deferred_widget.dart`` 中，系统构建了一个高效的异步代码装载状态机，并引入了**静态记忆化缓存（Static Memoization Cache）**：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ DeferredWidget 运行时状态机 (支持全局静态去重与瞬时恢复)                   │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 静态缓存池:                                                               │
   │ • static final Map<LibraryLoader, Future<void>> _moduleLoaders           │
   │ • static final Set<LibraryLoader> _loadedModules                         │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. 首次进入 (未加载状态):                                                 │
   │    • 触发: DeferredWidget.preload(libraryLoader)                          │
   │    • 动作: 发起 HTTP 请求拉取代码分片，存入 _moduleLoaders 拦截重复请求    │
   │    • 视图: build() 立即返回 DeferredLoadingPlaceholder 居中占位菊花       │
   │                                                                          │
   │ 2. 网络下载完成 (回调完成态):                                             │
   │    • 动作: _loadedModules.add(loader) 将模块标记为已落入内存              │
   │    • 触发: setState() ──► 执行 createWidget() 实例化真实子应用            │
   │    • 视图: 真实业务视图 (如 RallyApp) 瞬间替换占位菊花                   │
   │                                                                          │
   │ 3. 二次进入 (已加载命中态):                                               │
   │    • 判定: _loadedModules.contains(widget.libraryLoader) == true         │
   │    • 动作: 0 毫秒同步直接执行 _onLibraryLoaded()，跳过 Future 调度        │
   │    • 视图: 真实视图毫秒级直接渲染，完全无任何占位闪烁                     │
   └──────────────────────────────────────────────────────────────────────────┘

1. 全局请求去重与并发合并
~~~~~~~~~~~~~~~~~~~~~~~~~
* 若多个页面或路由同时请求同一个模块，``preload()`` 通过检查 ``_moduleLoaders.containsKey(loader)`` 直接复用正在进行中的 ``Future``，杜绝了重复发起网络请求的带宽浪费；
* 当模块一旦成功装载并打上 ``_loadedModules`` 标记后，后续所有导航跳转均在当前调用栈中以**同步方式瞬间构造视图**，达到了与静态编译完全相同的秒开性能。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 04 第 1 节：``04_gallery_routes_and_codeviewer/01_regex_routes_and_deferred.rst`` 已全量落盘完工**！系统拆解了 RouteConfiguration 正则捕获组寻址、Web 去动画与双屏路由分流、Dart deferred as 编译分包物理学、以及 DeferredWidget 记忆化状态机。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 04 第 2 节：``04_gallery_routes_and_codeviewer/02_codeviewer_ast_engine.rst``**。
  我们将深入 ``cxyFork-gallery/lib/codeviewer/`` 源码，系统剖析 CodeViewer 源码查看器引擎的 **AST 词法语法分词高亮、正则表达式关键字捕获、演示视图与源码视图双向联动、以及跨端剪贴板同步机制**。
