========================================================================================
第 1 节：InheritedElement 存储拓扑、O(1) 祖先哈希查找与 Aspect 细粒度订阅
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``flutter-3.32.0/packages/flutter/lib/src/widgets/framework.dart`` 与 ``packages/flutter/lib/src/widgets/inherited_model.dart``
   * **底层依赖源码**：``packages/flutter/lib/src/widgets/inherited_notifier.dart`` 与 ``packages/flutter/lib/src/widgets/inherited_theme.dart``
   * **核心使命**：以 Flutter 原生状态分发与依赖追踪体系为基准，深度解构 ``InheritedElement`` 在内存中的存储拓扑架构、基于不可变浅拷贝字典的 ``_inheritedElements`` 祖先哈希映射表（如何实现跨越数十层组件树的 $O(1)$ 瞬时查找）、双向依赖绑定建立与生命周期解绑机制、``notifyClients`` 遍历 ``_dependents`` 的脏节点标记流水线、以及 ``InheritedModel`` 基于切片（Aspect）的细粒度部分更新微观机理。

----------------------------------------------------------------------------------------

第一幕：跨层数据传递的物理困境与 $O(1)$ 祖先哈希表拓扑
------------------------------------------------------

在拥有数百个节点的大型组件树中，若深层叶子节点需要访问顶层祖先的状态数据（例如主题 ``Theme``、多语言 ``Locale`` 或全局状态 ``ModelBinding``）：

* **反模式 1：属性逐层透传（Prop Drilling）**：数十层中间容器必须在构造函数中显式声明并传递该参数，导致严重的模块耦合与样板代码爆炸；
* **反模式 2：运行时递归向上搜寻（Recursive Tree Walking）**：若在每次 ``build()`` 时顺着 ``parent`` 指针逐级向上递归查找目标祖先，查找时间复杂度为 $O(	ext{Depth})$。在深度为 50 的复杂树中，成百上千个叶子节点同时寻址将引发严重的 CPU 瓶颈与帧率掉帧。

Flutter 架构师在 ``Element`` 基类中设计了极其优雅的**静态祖先哈希字典拓扑（Ancestral Hash Map Topology）**：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ Element._inheritedElements 祖先哈希映射表拓扑                             │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 根节点 (RootElement):                                                    │
   │    • _inheritedElements = null                                           │
   │                                                                          │
   │ [挂载 Theme.InheritedTheme] (InheritedElement A):                         │
   │    • 触发 _updateInheritance()                                           │
   │    • 浅拷贝父级字典并写入自身:                                            │
   │      _inheritedElements = { Theme: InheritedElement_A }                  │
   │                                                                          │
   │    [挂载 MediaQuery] (InheritedElement B):                               │
   │       • 触发 _updateInheritance()                                        │
   │       • 浅拷贝父级字典并写入自身:                                         │
   │         _inheritedElements = { Theme: InheritedElement_A,                 │
   │                                MediaQuery: InheritedElement_B }          │
   │                                                                          │
   │       [深层叶子普通组件] (StatelessElement C, 嵌套深度 30 层):            │
   │          • 触发 _updateInheritance(): 直接共享引用父级的 _inheritedElements│
   │          • 调用 context.dependOnInheritedWidgetOfExactType<Theme>():     │
   │            直接执行 _inheritedElements[Theme] ──► 0 毫秒 O(1) 瞬时直达！ │
   └──────────────────────────────────────────────────────────────────────────┘

1. 继承表的按需浅拷贝与引用共享机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
查看 ``Element._updateInheritance()`` 的底层源码实现：

* **普通节点（非 InheritedElement）**：
  普通组件在挂载（``mount``）时，其内部的 ``_inheritedElements`` 指针**直接指向父节点的 `_inheritedElements` 内存地址**，完全不消耗额外的内存拷贝开销；
* **`InheritedElement` 节点**：
  当一个 ``InheritedElement`` 挂载时，它以父级的 ``_inheritedElements`` 为基础执行一次浅拷贝（Shallow Copy），并将自身以自身的运行时类型（``runtimeType``）作为 Key 存入字典：
  $$	ext{newMap} = 	ext{HashMap.of}(	ext{parent.\_inheritedElements}); \quad 	ext{newMap}[	ext{this.widget.runtimeType}] = 	ext{this}$$
* **物理收益**：无论组件嵌套有多深（哪怕 100 层），任何子节点只需执行一次哈希寻址（``_inheritedElements[T]``），即可在 **$O(1)$ 常数时间内瞬时获取目标祖先的物理内存指针**。

----------------------------------------------------------------------------------------

第二幕：双向依赖建立与 `_dependents` 拓扑注册机制
-------------------------------------------------

单纯获取数据指针只需查表（如 ``getInheritedWidgetOfExactType``），但若要在祖先数据发生变更时**自动通知子节点重新构建**，必须在两者之间建立双向响应式链接。

这是通过 ``context.dependOnInheritedElement(ancestor, aspect: aspect)`` 闭环完成的：

.. code-block:: text

   子节点 Element (Consumer)                      祖先 InheritedElement (Provider)
   ┌───────────────────────────┐                 ┌───────────────────────────┐
   │ Set<InheritedElement>     │                 │ Map<Element, Object?>     │
   │ _dependencies;            │ ──(向后引用)──► │ _dependents;              │
   │                           │ ◄──(前向追踪)── │                           │
   │ 记录我依赖了哪些祖先状态    │                 │ 记录哪些子节点依赖了我      │
   └───────────────────────────┘                 └───────────────────────────┘
                 │                                             │
                 └────────────── 建立双向依赖闭环 ──────────────┘

1. 双向引用的具体注册时序
~~~~~~~~~~~~~~~~~~~~~~~~~
1. **祖先侧登记**：祖先 ``InheritedElement`` 将当前发起调用的子 ``Element`` 作为 Key 插入其内部的 ``_dependents`` 字典中，并将传入的 ``aspect``（切片标记）作为 Value 存储；
2. **子节点侧登记**：子 ``Element`` 将祖先 ``InheritedElement`` 的指针加入其内部的 ``_dependencies`` 哈希集合中；
3. **生命周期自动解绑（防止内存泄漏）**：
   当子节点从组件树中被移除（进入 ``deactivate`` 阶段）时，子节点自动遍历其 ``_dependencies`` 集合，将自身从所有祖先的 ``_dependents`` 字典中注销，从物理层面彻底根除了悬空指针与脏通知。

----------------------------------------------------------------------------------------

第三幕：状态变更传播与 `notifyClients` 脏节点标记流水线
-------------------------------------------------------

当父级组件调用 ``setState()`` 导致 ``InheritedWidget`` 重新实例化并注入新数据时，底层的变更传播流水线按以下四步精密展开：

.. code-block:: text

   [上层重建，生成新的 InheritedWidget]
                    │
                    ▼
   1. InheritedElement.update(newWidget)
                    │
                    ▼
   2. 调用 widget.updateShouldNotify(oldWidget) 进行真值裁决
                    │
                    ├─► 返回 false: 数据未发生实质变更 ──► 立即终止，零开销退出
                    │
                    ▼ 返回 true: 确认数据已变更
   3. 调用 InheritedElement.updated(oldWidget) ──► 触发 notifyClients(oldWidget)
                    │
                    ▼
   4. 遍历 _dependents 集合中的所有子 Element:
      • 调用 notifyDependent(oldWidget, dependent)
      • dependent.didChangeDependencies() ──► 触发回调
      • dependent.markNeedsBuild() ──► 仅将该子节点标记为 dirty 并在下一帧安排重绘！

1. 极速阻断与静态子树保护
~~~~~~~~~~~~~~~~~~~~~~~~~
* 若数据未发生改变（``updateShouldNotify`` 返回 ``false``），通知链在第二步瞬间被掐断，**整棵子树完全不发生任何重绘**；
* 即使返回 ``true``，框架也**仅仅只遍历 `_dependents` 集合中登记过的订阅者**并将其置为 Dirty；
* 树上其他几十个未调用过 ``.of(context)`` 的中间静态组件（如外层的 Padding、SizedBox、Card 等）完全被跳过，其 ``build()`` 方法一次也不会被执行。

----------------------------------------------------------------------------------------

第四幕：按需切片细粒度更新——`InheritedModel` 与 Aspect 架构
-----------------------------------------------------------

在复杂的全局状态模型中，一个不可变实体可能包含多个独立字段（如主题色 ``themeColor`` 与字体大小 ``fontSize``）。
* **原生 `InheritedWidget` 的粗粒度缺陷**：只要实体内部任何一个字段变了，所有调用了 ``.of(context)`` 的子组件都会无差别全部重绘，即使某个子组件只关心字体大小而完全不在乎颜色。

Flutter 在 ``packages/flutter/lib/src/widgets/inherited_model.dart`` 中引入了 **``InheritedModel``**：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ InheritedModel Aspect (切片订阅) 细粒度过滤机制                           │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 订阅端:                                                                  │
   │ • 组件 A: InheritedModel.inheritFrom<AppModel>(context, aspect: 'color') │
   │   _dependents 登记: { Element_A: 'color' }                               │
   │ • 组件 B: InheritedModel.inheritFrom<AppModel>(context, aspect: 'font')  │
   │   _dependents 登记: { Element_B: 'font' }                                │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 更新端 (当仅有 color 发生改变时):                                        │
   │ 1. 触发 isSupportedAspect(aspect) 校验                                  │
   │ 2. 遍历 _dependents 校验 updateShouldNotifyDependent:                    │
   │    • 检查 Element_A: 依赖 'color' == 变更 'color' ──► 标记 dirty 重绘    │
   │    • 检查 Element_B: 依赖 'font'  != 变更 'color' ──► 忽略跳过，零重绘！ │
   └──────────────────────────────────────────────────────────────────────────┘

通过引入集合交集判决方程（$	ext{dependencies} \cap 	ext{changedAspects} 
e \emptyset$），实现了字段级别的精准局部响应式重绘。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 07 第 1 节：``07_framework_state_and_gestures/01_inherited_element_hash_table.rst`` 已全量落盘完工**！
  深度解构了 ``InheritedElement`` 祖先哈希映射表的 $O(1)$ 查找拓扑、双向依赖注销与内存防漏机制、``notifyClients`` 局部脏节点遍历流水线、以及 ``InheritedModel`` 细粒度 Aspect 切片更新算法。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 07 第 2 节：``07_framework_state_and_gestures/02_listenable_and_changenotifier.rst``**。
  我们将深入 ``flutter-3.32.0/packages/flutter/lib/src/foundation/change_notifier.dart`` 源码，系统剖析 ``Listenable`` 与 ``ChangeNotifier`` 的观察者物理内存结构、动态扩容监听器数组（``_listeners``）、通知重入保护、微任务合并、以及 ``ListenableBuilder`` vs ``AnimatedBuilder`` 的零冗余内存开销机制。
