========================================================================================
第 2 节：Element 树的生命周期、挂载 (mount)、复用与卸载机制
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``flutter-3.32.0/packages/flutter/lib/src/widgets/framework.dart``
   * **底层依赖源码**：``packages/flutter/lib/src/rendering/object.dart`` 与 ``packages/flutter/lib/src/foundation/diagnostics.dart``
   * **核心使命**：以 Flutter 运行时真正的内存骨架为基准，深度解构为什么 ``BuildContext`` 在物理上就是 ``Element`` 自身的指针引用、``_ElementLifecycle`` 四态生命周期状态机（``initial`` $	o$ ``active`` $	o$ ``inactive`` $	o$ ``defunct``）、深度优先树状挂载（``mount``）时序、以及 ``ComponentElement`` 逻辑节点与 ``RenderObjectElement`` 物理渲染节点的拓扑分化。

----------------------------------------------------------------------------------------

第一幕：`BuildContext` 的物理真相——Element 节点的自引用中枢
------------------------------------------------------------

在 Flutter 应用开发中，开发者在每一个 ``build(BuildContext context)`` 方法中都会接触到 ``context``。

然而在框架源码中（``framework.dart`` 第 2900 行）：

.. code-block:: text

   abstract class Element extends DiagnosticableTree implements BuildContext {
     ...
   }

1. `BuildContext` 的内存物理本质
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **物理事实**：``BuildContext`` **根本不是某种独立的数据上下文对象，它就是当前位置的 `Element` 实例自身**；
* 框架为了防止开发者在 UI 层直接篡改 Element 的生命周期指针（如非法调用 ``mount()`` 或 ``unmount()``），特意提取了一个纯虚接口 ``BuildContext``；
* 当你在代码里写 ``Theme.of(context)`` 或 ``Navigator.of(context)`` 时，本质上是拿着当前 ``Element`` 节点的指针，在组件树中进行向上寻址或注册依赖。

2. 依托于 Element 的树状寻址能力
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
作为树上的实体节点，``Element`` 原生具备四维寻址能力：
* **祖先遍历 (`findAncestorStateOfType`)**：顺着 ``_parent`` 链表指针向上回溯，查找最近的匹配状态实例；
* **环境依赖绑定 (`dependOnInheritedWidgetOfExactType`)**：直接读取内部持有的 ``_inheritedElements`` 哈希表，实现 $O(1)$ 局部数据订阅；
* **物理渲染对象提取 (`findRenderObject`)**：递归穿透子树，定位最近的物理 ``RenderObject``。

----------------------------------------------------------------------------------------

第二幕：`_ElementLifecycle` 四态生命周期状态机微观推导
------------------------------------------------------

与轻量、瞬时创建即焚的 ``Widget`` 不同，``Element`` 是常驻在内存中的可变长生命周期实体。其内部严格受控于一个四态有限状态机：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ Element 四态生命周期状态机 (framework.dart)                               │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. _ElementLifecycle.initial (初始未挂载态):                             │
   │    • 触发: Widget.createElement() 刚在堆内存实例化                        │
   │    • 特征: _parent == null, 尚未接入组件树，无任何 slot 槽位              │
   │                                                                          │
   │ 2. _ElementLifecycle.active (激活在树态):                                │
   │    • 触发: 父节点调用 mount(parent, newSlot)                             │
   │    • 动作: 确立父子指针，初始化 State.initState()，注册到全局 BuildOwner  │
   │    • 状态: 允许调用 markNeedsBuild() 标记 dirty 并参与帧渲染              │
   │                                                                          │
   │ 3. _ElementLifecycle.inactive (失活暂存态):                              │
   │    • 触发: 父节点 Diff 失败调用 deactivateChild(child)                    │
   │    • 动作: 从父节点脱落，脱离 Render 树，推入 BuildOwner._inactiveElements│
   │    • 关键: State.deactivate() 触发，本帧内允许被 GlobalKey 抢救重挂载    │
   │                                                                          │
   │ 4. _ElementLifecycle.defunct (彻底销毁态):                               │
   │    • 触发: 本帧末尾 BuildOwner.finalizeTree() 扫描回收桶                  │
   │    • 动作: 深度优先调用 unmount()，触发 State.dispose()，释放监听器       │
   │    • 结果: 节点永久死亡，等待 Dart VM 垃圾回收器 (GC) 回收物理内存        │
   └──────────────────────────────────────────────────────────────────────────┘

1. 深度优先挂载时序 (`mount`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当根节点启动或新子节点插入时，``mount(parent, newSlot)`` 开启递归构建：
1. **确立祖先拓扑**：将 ``_parent = parent``，并从父级复制最新的 ``_inheritedElements`` 哈希表引用；
2. **深度自增**：``_depth = parent != null ? parent.depth + 1 : 1``，该深度值在后续 Dirty 节点重绘排序中至关重要；
3. **驱动物理渲染树**：若为 ``RenderObjectElement``，在此步骤将自身创建的 ``RenderObject`` 插入到父级渲染节点的几何插槽（Slot）中；
4. **递归向下分裂**：调用 ``performRebuild()`` 触发子 Widget 的创建与子 Element 的递归挂载。

2. 失活回收桶（`_InactiveElements`）的缓冲机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当一个 Widget 在当前帧被从旧父级移除时，Flutter **绝不会立即销毁其对应的 Element**：
* 框架将其放入 ``BuildOwner._inactiveElements`` 临时集合中，状态置为 ``inactive``；
* 如果同一帧内，该组件携带的 ``GlobalKey`` 在树的另一个位置被声明插入，框架直接从回收桶中捞出该 Element 并调用 ``activateBy()`` 重挂载，内部的 ``State``、动画控制器和滚动偏移量得以 **100% 完整保留**；
* 只有在整帧管线渲染完毕（``finalizeTree``）时，仍未被认领的 Element 才会最终执行 ``unmount()`` 走向销毁。

----------------------------------------------------------------------------------------

第三幕：`ComponentElement` 与 `RenderObjectElement` 的拓扑分化
--------------------------------------------------------------

在继承树上，所有 Element 划分为两大截然不同的架构阵营：

.. code-block:: text

   Element 核心继承拓扑
        │
        ├── 1. ComponentElement (结构与逻辑编排节点)
        │        ├── StatelessElement  ── 对应 StatelessWidget (纯函数构建)
        │        ├── StatefulElement   ── 对应 StatefulWidget (持有可变 State)
        │        └── ProxyElement      ── 对应 InheritedElement (数据分发)
        │        ★ 特征: 自身不产生任何物理像素！仅在 performRebuild 时调用 build()
        │
        └── 2. RenderObjectElement (几何排版与物理渲染节点)
                 ├── LeafRenderObjectElement   ── 树叶节点 (如 Image, RawImage)
                 ├── SingleChildRenderObjectElement ── 单子节点 (如 Padding, Opacity)
                 └── MultiChildRenderObjectElement  ── 多子节点 (如 Flex, Stack)
                 ★ 特征: 拥有真实 RenderObject！负责将像素、约束与图层提交给 GPU

1. `ComponentElement` 的逻辑展开流水线
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* ``StatelessElement`` 执行 ``widget.build(this)``，将返回的单个子 Widget 传给 ``updateChild``；
* ``StatefulElement`` 在 ``mount`` 阶段首先调用 ``widget.createState()`` 实例化业务状态对象，并将状态的内部 ``_element`` 指针绑定为自身，随后驱动 ``state.build(this)``；
* 它们在屏幕上没有任何尺寸和坐标，它们存在的唯一意义就是**将复杂的业务逻辑分解为更基础的渲染原子组件**。

2. `RenderObjectElement` 的物理绑定流水线
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 在 ``mount`` 阶段，调用 ``widget.createRenderObject(this)`` 创建底层的 ``RenderObject``；
* 通过 ``attachRenderObject(newSlot)`` 找到祖先链上最近的 ``RenderObjectElement``，将新创建的物理渲染对象挂载到渲染树中；
* 当 Widget 属性发生变更（但类型和 Key 相同）时，框架不会销毁 RenderObject，而是调用 ``widget.updateRenderObject(this, renderObject)`` 在原地就地修改渲染属性，实现了极速的增量属性刷新。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 05 第 2 节：``05_framework_three_trees/02_element_lifecycle_and_mount.rst`` 已全量落盘完工**！系统拆解了 BuildContext 的物理自引用本质、Element 四态生命周期状态机、_InactiveElements 回收桶缓冲机制、以及 ComponentElement 与 RenderObjectElement 的分化挂载拓扑。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 05 第 3 节：``05_framework_three_trees/03_diff_algorithm_and_keys.rst``**。
  我们将深入 ``flutter-3.32.0/packages/flutter/lib/src/widgets/framework.dart`` 源码中的 ``Element.updateChild`` 与 ``updateChildren``，系统剖析两级 Diff 算法的 4 种更新分支、双指针列表滑动复用算法、以及 ``ValueKey``、``ObjectKey`` 与 ``GlobalKey`` 跨父级重挂载（Reparenting）的底层物理机制。
