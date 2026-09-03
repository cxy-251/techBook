========================================================================================
第 3 节：updateChild 两级 Diff 算法与 Key 跨父级重挂载 (Reparenting) 原理
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``flutter-3.32.0/packages/flutter/lib/src/widgets/framework.dart``
   * **底层依赖源码**：``packages/flutter/lib/src/foundation/key.dart`` 与 ``packages/flutter/lib/src/rendering/object.dart``
   * **核心使命**：以响应式渲染树的高性能调和（Reconciliation）算法为基准，深度解构 Flutter 3.32 框架中 ``Element.updateChild`` 的四大分支状态转移矩阵、多子节点列表 ``RenderObjectElement.updateChildren`` 基于双端指针与哈希定位的六步 Diff 算法、``LocalKey``（``ValueKey`` / ``ObjectKey``）的同级比对机制、以及 ``GlobalKey`` 依托 ``BuildOwner._globalKeyRegistry`` 实现跨父级节点移动重挂载（Reparenting）与状态无损迁移的物理底层。

----------------------------------------------------------------------------------------

第一幕：单节点调和中枢——`Element.updateChild` 四大物理分支
----------------------------------------------------------

在 Flutter 整个框架层，所有的组件树增删改查最终都会收敛到 ``Element.updateChild(Element? child, Widget? newWidget, Object? newSlot)``。

该方法构成了 Flutter 声明式 UI 驱动命令式渲染树的核心状态转移矩阵：

.. code-block:: text

   ┌───────────────────┬──────────────────────────┬──────────────────────────┐
   │ updateChild 决策表 │ newWidget == null        │ newWidget != null        │
   ├───────────────────┼──────────────────────────┼──────────────────────────┤
   │ child == null     │ 分支 1: 保持空值          │ 分支 2: 新建节点         │
   │                   │ 返回 null                │ 调用 inflateWidget()     │
   ├───────────────────┼──────────────────────────┼──────────────────────────┤
   │ child != null     │ 分支 3: 销毁节点         │ 分支 4: 增量复用或置换   │
   │                   │ 调用 deactivateChild()   │ 比对 canUpdate 决定更新  │
   └───────────────────┴──────────────────────────┴──────────────────────────┘

1. 分支 4：增量更新的三级短路判定
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当新旧节点均非空时，框架按序执行三级判定：

* **第一级：对象引用恒等（`child.widget == newWidget`）**：
  * 若为同一个内存实例（如 ``const Widget`` 或被 State 变量缓存的对象），框架**完全跳过该子树的全部 Diff 与 Rebuild 工作**，仅在插槽（``slot``）发生移动时调用 ``updateSlotForChild()``，以 0 开销实现瞬时短路；
* **第二级：类型与 Key 匹配（`Widget.canUpdate(old, new) == true`）**：
  * 若 ``old.runtimeType == new.runtimeType && old.key == new.key``，框架保留现有的 ``Element`` 与底层的 ``RenderObject``；
  * 调用 ``child.update(newWidget)`` 将新 Widget 属性就地覆盖到 Element，并触发关联 State 的 ``didUpdateWidget()``；
* **第三级：失配置换（`canUpdate == false`）**：
  * 若类型或 Key 不匹配，框架调用 ``deactivateChild(child)`` 将旧 Element 剥离并推入失活回收桶，随后调用 ``inflateWidget(newWidget, newSlot)`` 实例化全新的 Element。

----------------------------------------------------------------------------------------

第二幕：多子列表 Diff 算法——`updateChildren` 双端指针与哈希对齐
----------------------------------------------------------------

在 ``MultiChildRenderObjectElement.updateChildren`` 中，面对动态列表的插入、删除、重排操作，若采用简单的同下标逐项对比，任何头部插入都会导致后续所有节点被错误识别为“类型改变”而全量销毁重建。

Flutter 实现了一套基于**双端收缩指针与哈希定位的六步 Diff 算法**：

.. code-block:: text

   [旧子节点列表: oldChildren]  vs  [新子组件列表: newWidgets]
   ───────────────────────────────────────────────────────────────────────────
   步骤 1: 顶部正向同步 ──► 从 index 0 向后扫描，直到命中首个 canUpdate 失败节点
   步骤 2: 底部反向收缩 ──► 从末尾倒序向前扫描，圈定未匹配的中间混乱区间 [Top, Bottom]
   步骤 3: 建立旧键哈希表 ──► 遍历旧列表中间区间，将带 Key 的 Element 存入 oldKeyedChildren
   步骤 4: 中间正向对齐 ──► 遍历新列表中间区间:
           • 若带 Key 且在 oldKeyedChildren 命中: 提取复用并从哈希表移除
           • 若未带 Key 或未命中: 传入 null 触发 inflateWidget() 构造新节点
   步骤 5: 底部节点同步 ──► 处理步骤 2 暂存的底部连续匹配节点
   步骤 6: 残余节点清理 ──► 将 oldKeyedChildren 中未被认领的旧节点统一调用 deactivateChild()

1. 双端指针收缩的性能优势
~~~~~~~~~~~~~~~~~~~~~~~~~
* 对于常见的“列表头部插入新项”或“列表尾部追加项”，步骤 1 与步骤 2 能在 $O(1)$ 时间内迅速将不变的头部与尾部直接对齐复用，将需要进行昂贵哈希计算的范围缩小到最小区间；
* 整体算法时间复杂度严格维持在 **$O(N)$ 线性级别**，极大降低了万级列表滑动时的重构压力。

----------------------------------------------------------------------------------------

第三幕：Key 类型系统与 `GlobalKey` 跨父级重挂载 (Reparenting)
-------------------------------------------------------------

在 Flutter 中，``Key`` 是控制 Element 是否能与 Widget 配对的唯一物理凭据，分为局部键与全局键两大体系：

.. code-block:: text

   Key 类型继承矩阵
        │
        ├── 1. LocalKey (同级同父作用域)
        │        ├── ValueKey<T>   ── 基于值相等性比对 (operator ==)
        │        ├── ObjectKey     ── 基于对象内存指针比对 (identical)
        │        └── UniqueKey     ── 每次实例化生成唯一标识 (禁止复用)
        │        ★ 职责: 仅用于 updateChildren 在同父级的列表内识别节点位置变动
        │
        └── 2. GlobalKey (全应用全局唯一凭据)
                 ├── LabeledGlobalKey  ── 调试标记全局键
                 └── GlobalObjectKey   ── 绑定特定对象的全局键
                 ★ 职责: 注册于 BuildOwner 全局注册表，支持跨父级无损迁移 (Reparenting)

1. `GlobalKey` 跨父级重挂载的微观执行链路 (`_retakeInactiveElement`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当一个带有 ``GlobalKey`` 的组件在同一帧内从父节点 A 移动到父节点 B 时（如从屏幕顶部列表拖入底部容器）：

.. code-block:: text

   [父节点 B 调用 inflateWidget(newWidget)]
                      │
                      ▼
   1. 检测到 newWidget.key is GlobalKey
                      │
                      ▼
   2. 调用 _retakeInactiveElement(key, newWidget)
      • 从 BuildOwner._globalKeyRegistry 中精准定位该 key 绑定的已有 Element
                      │
                      ▼
   3. 从旧父节点 A 主动夺取 (Proactive Steal):
      • 调用 oldParent.forgetChild(element) ──► 从旧父级的子列表中剔除
      • 调用 oldParent.deactivateChild(element) ──► 将其 RenderObject 从旧渲染树脱落
                      │
                      ▼
   4. 将该 Element 直接绑定至新父节点 B:
      • newChild._activateWithParent(this, newSlot)
      • 递归更新 _depth 与 _buildScope
      • 重新将 RenderObject 插入新父级的几何插槽
                      │
                      ▼
   5. 结果: Element 内部持有的 State 实例、动画控制器与滚动进度 100% 完整保留！

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 05 第 3 节：``05_framework_three_trees/03_diff_algorithm_and_keys.rst`` 已全量落盘完工**！系统拆解了 updateChild 四大分支状态矩阵、updateChildren 双端收缩六步 Diff 算法、LocalKey 与 GlobalKey 的架构分化、以及 GlobalKey 跨父级无损重挂载的物理实现。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 05 第 4 节：``05_framework_three_trees/04_build_owner_dirty_scope.rst``**。
  我们将深入 ``flutter-3.32.0/packages/flutter/lib/src/widgets/framework.dart`` 源码中的 ``BuildOwner`` 与 ``BuildScope``，系统剖析脏节点收集队列、基于 Element 深度（``_depth``）的升序排序重构算法（确保父节点永远先于子节点构建）、以及防止在 build 期间非法调用 ``setState()`` 的状态锁定安全屏障（``lockState``）。
