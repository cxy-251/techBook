========================================================================================
第 2 节：gallery_options.dart 不可变状态、ModelBinding 与 InheritedElement 深度解构
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``cxyFork-gallery/lib/data/gallery_options.dart``
   * **底层依赖源码**：``flutter-3.32.0/packages/flutter/lib/src/widgets/framework.dart`` (InheritedWidget / InheritedElement)
   * **核心使命**：以底层框架机制为尺，深度解构 Gallery 如何在完全不引入 Provider、Bloc 或 Redux 等外部依赖的前提下，利用不可变数据模型（Immutable Data Model）与原生 ``InheritedWidget`` / ``InheritedElement`` 依赖哈希表，实现全 App 全局状态的 $O(1)$ 复杂度收集与定向精准重绘。

----------------------------------------------------------------------------------------

第一幕：不可变数据实体与 `copyWith` 增量克隆物理机制
------------------------------------------------------

在状态管理架构中，最大的性能杀手与 Bug 来源是“可变共享状态（Shared Mutable State）”——多个组件持有同一个对象的内存指针，并在异步任务中随意修改其内部属性，导致脏读、状态竞争与无法预测的界面撕裂。

在 ``lib/data/gallery_options.dart`` 中，整个应用的全局环境状态被严格封装为不可变实体类 ``GalleryOptions``：

1. 字段不可变性与线程安全
~~~~~~~~~~~~~~~~~~~~~~~~~
* 类的所有属性均声明为 ``final``：
  * ``ThemeMode themeMode``：深色、浅色或跟随系统；
  * ``double _textScaleFactor``：字号缩放比例；
  * ``CustomTextDirection customTextDirection``：文本排版方向（LTR 从左至右，RTL 从右至左）；
  * ``Locale? _locale``：当前激活的国际化语言环境；
  * ``double timeDilation``：动画慢放倍率（用于调试慢动作渲染）；
  * ``TargetPlatform? platform``：目标平台模拟（在 macOS 上模拟 iOS/Android 行为）；
  * ``bool isTestMode``：集成测试开关。
* **物理收益**：对象一旦在堆内存中被实例化，其物理内存二进制内容即被完全固化。任何函数、异步回调或子组件均无法篡改其已有属性，从结构上保证了多线程与并发场景下的绝对安全性。

2. `copyWith` 增量克隆范式
~~~~~~~~~~~~~~~~~~~~~~~~~~
当用户在深层设置页面修改了某一项设置（例如将主题由浅色改为深色）时，系统绝不直接修改已有对象的内存字段，而是调用 ``copyWith`` 方法：

* **增量构造原理**：
  ``copyWith`` 接收可选命名参数，并使用空值合并运算符（``??``）：
  * 传入了新值的字段采用新值；
  * 未传入新值的字段，直接引用旧对象内部原有的属性指针（``themeMode ?? this.themeMode``）；
* **浅比较判定（Identity Comparison）**：
  框架通过重写 ``operator ==`` 与 ``hashCode``，将 7 个核心属性通过 ``Object.hash`` 进行联合哈希计算。当新旧配置发生比对时，若哈希值完全一致，框架可在 **1 个时钟周期** 内直接判定无实质变更，从而快速拦截无意义的下游重绘。

3. 哨兵值机制与语言方向解析
~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **哨兵值（Sentinel Value）**：针对文字缩放，使用常量 ``systemTextScaleFactorOption`` 作为特殊哨兵。当用户选择“跟随系统”时，方法动态返回底层 ``MediaQuery.of(context).textScaleFactor``，否则返回用户强制指定的硬编码缩放数值；
* **RTL 语言启发式匹配**：在 ``resolvedTextDirection()`` 中，内置了阿拉伯语（ar）、波斯语（fa）、希伯来语（he）、普什图语（ps）、乌尔都语（ur）等从右向左书写的语言列表。系统自动提取当前 Locale 的语言代码，动态求解并返回 ``TextDirection.rtl`` 或 ``TextDirection.ltr``。

----------------------------------------------------------------------------------------

第二幕：架构解耦——`ModelBinding` 与 `_ModelBindingScope` 的双层中枢
----------------------------------------------------------------------

在状态管理架构中，Gallery 采用了职责高度解耦的“控制中枢 + 广播发射塔”双层物理结构：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────┐
   │ 1. ModelBinding (StatefulWidget - 可变控制器)                     │
   │    • 物理职责: 在内部 State 中持有唯一的真实数据实例 currentModel     │
   │    • 对外接口: updateModel(newModel) ──> 触发 setState()         │
   └────────────────────────────────┬─────────────────────────────────┘
                                    │ 每次 setState 时重新生成
                                    ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │ 2. _ModelBindingScope (InheritedWidget - 不可变广播发射塔)        │
   │    • 物理职责: 挂载于整棵视图树的最高层 (MaterialApp 之上)           │
   │    • 核心裁决: updateShouldNotify(_ModelBindingScope oldWidget)    │
   │    • 内部引用: 持有 _ModelBindingState 的指针引用 (用于子节点反向调用)│
   └──────────────────────────────────────────────────────────────────┘

1. 状态持有者：`ModelBindingState`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 继承自 ``State<ModelBinding>``，在 ``initState()`` 时装载初始配置 ``initialModel``；
* **慢动作调试拦截 (`handleTimeDilation`)**：
  当用户调整动画慢放因子时，系统不会立即突变，而是启动一个 150 毫秒的延时定时器（``Timer``），等待用户肉眼看到按钮点击反馈后，再将全局的 ``timeDilation`` 变慢，给开发者呈现出极其平滑的物理调试体验；
* 当收到 ``updateModel(newModel)`` 调用且新旧模型不相等时，调用原生的 ``setState()``，驱动子树执行重新构建。

2. 广播发射塔：`_ModelBindingScope`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 继承自 ``InheritedWidget``，将 ``modelBindingState`` 自身作为属性向下透传；
* 重写核心裁决方法 ``updateShouldNotify(_ModelBindingScope oldWidget) => true``，告知框架层：“只要我被重新构建，请立即启动下游依赖节点的定向通知与刷新”。

----------------------------------------------------------------------------------------

第三幕：`InheritedElement` 底层依赖收集与 $O(1)$ 局部精准重绘机制
------------------------------------------------------------------

这套架构最精妙的核心，在于它完全依赖 Flutter 框架底层的 ``InheritedElement`` 依赖哈希表机制，实现了 **零冗余重绘与理论最优的时间复杂度**：

.. code-block:: text

   [子组件调用: GalleryOptions.of(context)]
                      │
                      ▼
   1. context.dependOnInheritedWidgetOfExactType<_ModelBindingScope>()
                      │
                      ▼ (查询当前 Element 内部的 _inheritedElements 哈希表)
   2. O(1) 瞬时定位到根部的 _ModelBindingScope 对应的 InheritedElement
                      │
                      ▼
   3. 框架将当前子 Element 注册进 InheritedElement 的依赖集合:
      InheritedElement._dependents[childElement] = null
                      │
   ═══════════════════╪═════════════════════════════════════════════════
                      │ (未来时刻: 用户在设置页修改主题)
                      ▼
   4. GalleryOptions.update(context, newOptions) ──> 触发 setState()
                      │
                      ▼
   5. 根部 InheritedElement.update(newWidget) 执行
                      │
                      ▼
   6. 调用 updateShouldNotify(oldWidget) ──> 返回 true
                      │
                      ▼
   7. 触发 InheritedElement.notifyClients()
                      │
                      ▼
   8. 仅遍历 _dependents 哈希表中的子节点 ──> 执行 child.didChangeDependencies()
                      │
                      ▼
   9. 仅将这几个订阅了状态的叶子节点标记为 Dirty，并在下一帧触发局部 build()

1. $O(1)$ 复杂度的查找真相
~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 初学者常误以为 ``.of(context)`` 需要顺着树枝一层层往上递归父节点（$O(N)$ 复杂度）；
* **底层物理真相**：在 Flutter 3.32 框架源码（``framework.dart``）中，每个 ``Element`` 节点被挂载（mount）到树上时，会自动从父节点**浅拷贝（Inherit）一份祖先 InheritedElement 的引用哈希表**（``_inheritedElements``）；
* 因此，在树的任意深处调用 ``.of(context)``，本质上只是在这张哈希表中执行了一次以类名 Type 为 Key 的取值操作，耗时恒定为 **$O(1)$ 纳秒级操作**。

2. 依赖收集与定向唤醒 (`notifyClients`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 当子节点调用 ``.of(context)`` 时，框架自动将当前子节点的 ``Element`` 指针写入 ``InheritedElement`` 内部维护的 ``_dependents`` 集合中；
* 当配置更新触发 ``notifyClients()`` 时，框架**绝对不会遍历整棵组件树**，而是仅沿着 ``_dependents`` 集合，将真正调用过配置的子节点执行 ``didChangeDependencies()`` 并标记为 Dirty；
* 中间成百上千个未订阅配置的静态组件（如普通 Container、Text、图片），在整个更新周期中**完全不被唤醒、不执行任何 build() 代码**，实现了极致的高帧率局部渲染。

----------------------------------------------------------------------------------------

第四幕：`ApplyTextOptions` 响应式文本与方向性装饰器
----------------------------------------------------

在 ``lib/data/gallery_options.dart`` 的末尾，封装了一个关键的中间层组件 ``ApplyTextOptions``：

* **动态媒体查询覆盖 (`MediaQuery.copyWith`)**：
  它从全局配置中提取当前计算得出的 ``textScaleFactor``，并利用局部 ``MediaQuery`` 将该数值覆盖注入到子树中，确保下层所有 Material 文本组件能够自动响应全局字号滑动条的调节；
* **文字排版方向性注入 (`Directionality`)**：
  若当前语言被识别为阿拉伯语等 RTL 语系，组件自动在最外层包裹 ``Directionality(textDirection: TextDirection.rtl)``，使整棵视图树的水平布局（如 Row、图标对齐、文本边距）在底层自动产生物理镜像反转，实现真正无缝的全球化排版适配。

----------------------------------------------------------------------------------------

小结与给下一个对话的建议 (Summary & Next Step Advisory)
--------------------------------------------------------

* **本章核心产出**：
  深入解构了不可变实体类 ``GalleryOptions`` 的设计哲学、``copyWith`` 浅克隆范式、``ModelBinding`` 双层中枢架构，以及 ``InheritedElement`` 依赖哈希表在 $O(1)$ 查找与定向局部重绘上的底层物理执行流。
* **给下一个对话的施工建议**：
  下一个对话将严格聚焦 **模块 01 第 3 节：``01_gallery_foundation/03_theme_and_tokens.rst``**。
  我们将深入 ``gallery_theme_data.dart`` 源码，系统剖析生产级设计令牌（Design Tokens）、语义化颜色系统（ColorScheme 的深浅色角色分配与对比度物理计算）、以及基于 Google Fonts 的多端字体拓扑规范。
