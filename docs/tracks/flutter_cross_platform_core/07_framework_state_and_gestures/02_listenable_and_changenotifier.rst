========================================================================================
第 2 节：ChangeNotifier 内存拓扑、重入保护、重构调度与 Listenable 体系
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``flutter-3.32.0/packages/flutter/lib/src/foundation/change_notifier.dart`` 与 ``packages/flutter/lib/src/widgets/value_listenable_builder.dart``
   * **底层依赖源码**：``packages/flutter/lib/src/widgets/transitions.dart`` 与 ``packages/flutter/lib/src/foundation/memory_allocations.dart``
   * **核心使命**：以 Flutter 观察者模式与微观内存管理为基准，深度解构 ``Listenable`` 与 ``ValueListenable`` 抽象契约体系、``ChangeNotifier`` 基于定长数组倍增（$2	imes$）与 50% 滞后收缩的高性能内存拓扑、嵌套通知与监听器移除的重入深度保护机制（``_notificationCallStackDepth``）、``ValueNotifier<T>`` 的对象身份比对陷阱、以及 ``ListenableBuilder`` 基于预构建 ``child`` 的子树重绘隔离性能优化。

----------------------------------------------------------------------------------------

第一幕：观察者模式的底层抽象——`Listenable` 与 `ValueListenable` 协议
----------------------------------------------------------------------

在响应式 UI 体系中，状态数据与视图组件的解耦依赖于发布-订阅（Pub-Sub）机制。Flutter 在基础库（Foundation）中定义了极简的单向通知协议：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ Listenable 接口体系类继承拓扑                                            │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ Listenable (抽象基类)                                                    │
   │    ├── addListener(VoidCallback listener)    (注册无参回调)              │
   │    └── removeListener(VoidCallback listener) (注销回调)                  │
   │           ▲                                                              │
   │           │ 扩展值语义                                                   │
   │           │                                                              │
   │ ValueListenable<T>                                                       │
   │    └── T get value; (对外暴露当前类型为 T 的只读状态值)                   │
   │           ▲                                                              │
   │           ├── ValueNotifier<T> (单值响应式可变容器)                      │
   │           └── Animation<T>     (带插值与方向状态的时间驱动器)            │
   └──────────────────────────────────────────────────────────────────────────┘

1. 为什么采用零参数 `VoidCallback`？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* ``addListener(VoidCallback listener)`` 严格规定回调函数不接受任何参数（``void Function()``）；
* **设计意图**：强制状态订阅者（如 UI 组件）主动从数据源提取所需切片，防止通知管道成为数据载体引发跨层数据耦合与装箱/拆箱（Boxing）开销。

----------------------------------------------------------------------------------------

第二幕：`ChangeNotifier` 物理内存拓扑与极致性能调优
----------------------------------------------------

在 Dart 虚拟机中，动态扩容集合（如普通 ``List.empty(growable: true)``）在频繁插入和删除元素时会产生大量的数组复制与垃圾回收压力。``ChangeNotifier`` 在底层实现了自研的高性能定长数组管理策略：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ ChangeNotifier 内部定长数组内存拓扑与扩容机制                             │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. 初始状态 (Count = 0):                                                 │
   │    • _listeners = _emptyListeners (共享静态定长空列表，0 内存开销)        │
   │                                                                          │
   │ 2. 插入首个监听器 (Count = 1):                                           │
   │    • 分配容量为 1 的定长数组: _listeners = [ Listener_0 ]                 │
   │                                                                          │
   │ 3. 数组填满时的倍增分配 (Count == _listeners.length):                     │
   │    • 分配容量翻倍的新数组: newListeners = List.filled(length * 2, null)  │
   │    • 原生浅拷贝搬运旧元素，将单次插入均摊时间复杂度稳定在 O(1)            │
   │                                                                          │
   │ 4. 50% 滞后收缩防抖机制 (_removeAt):                                     │
   │    • 仅当实际元素数 _count * 2 <= _listeners.length 时才触发内存收缩      │
   │    • 杜绝在临界容量附近“频繁添加/删除”引发的内存反复分配震荡 (Thrashing)   │
   └──────────────────────────────────────────────────────────────────────────┘

1. 重入调用栈深度追踪与延迟清理 (`_notificationCallStackDepth`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
若某个监听器在执行过程中，其内部代码再次调用了 ``removeListener()`` 注销了后续某个尚未被调用的监听器，或者递归调用了 ``notifyListeners()``：

* **并发修改异常危机**：直接在循环遍历中缩容数组（``removeAt``）会导致索引错位，跳过后续监听器或触发越界崩溃；
* **物理防重入标记解法**：
  1. 进入 ``notifyListeners()`` 瞬间，将调用栈深度自增：``_notificationCallStackDepth++``；
  2. 在迭代期间，若触发 ``removeListener``，系统**不缩容数组，仅将该槽位就地置为 `null`**，并递增 ``_reentrantlyRemovedListeners``；
  3. 当且仅当所有递归调用全部退出（``_notificationCallStackDepth == 0``）时，系统才在末尾启动一次性的数组空位压缩与真实缩容。

2. 异常隔离与全链路保活
~~~~~~~~~~~~~~~~~~~~~~~
在遍历通知监听器列表时，每个调用均被严格包裹在 ``try-catch`` 块中：
* 单个监听器内部抛出的未捕获异常会被 ``FlutterError.reportError`` 上报给诊断树；
* **异常不会阻断循环**：后续的监听器依然能够正常收到通知并推进 UI 更新，确保了核心界面状态的健壮性。

----------------------------------------------------------------------------------------

第三幕：`ValueNotifier<T>` 的身份相等性陷阱与防抖机理
------------------------------------------------------

``ValueNotifier<T>`` 继承自 ``ChangeNotifier``，其 Setter 方法包含了严格的防抖拦截：

.. code-block:: text

   set value(T newValue) {
     if (_value == newValue) {
       return; // 物理值未改变，立即拦截，零通知开销
     }
     _value = newValue;
     notifyListeners();
   }

1. 可变集合（Mutable Collections）的隐蔽失效陷阱
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **反模式**：若实例化一个 ``ValueNotifier<List<int>> notifier``，并在代码中执行 ``notifier.value.add(42)``；
* **失效原因**：虽然列表内部元素增加了，但 ``_value`` 与 ``newValue`` 指向的是堆内存中的同一个 ``List`` 实例（指针引用完全相等，``_value == newValue`` 判定为 ``true``）；
* **结果**：Setter 中的防抖检查直接返回，``notifyListeners()`` 永远不会被触发，UI 保持死寂！
* **工程铁律**：``ValueNotifier`` **必须严格搭配不可变数据类型（Immutable Types）**使用，通过克隆新对象（如 ``List.from()`` 或 ``copyWith``）重新触发赋值。

----------------------------------------------------------------------------------------

第四幕：`ListenableBuilder` 局部子树隔离与零开销重绘
----------------------------------------------------

在传统开发中，直接在根组件调用 ``setState()`` 会迫使下层所有子组件无差别重新执行 ``build()``。

``ListenableBuilder``（与 ``AnimatedBuilder`` 底层逻辑完全等价）提供了精确的**局部组件重绘边界**：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ ListenableBuilder 子树隔离拓扑                                           │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 外部静态组件树 (昂贵子树):                                               │
   │    final heavyChild = const ExpensiveComplexWidget();                    │
   │                                                                          │
   │ ListenableBuilder(                                                       │
   │    listenable: counterNotifier,                                          │
   │    child: heavyChild, // 传入预先构建好的子树指针                        │
   │    builder: (context, child) {                                           │
   │      // 仅此闭包内部发生局部重绘:                                        │
   │      return Column(                                                      │
   │        children: [                                                       │
   │          Text('${counterNotifier.value}'), // 仅此处重新取值               │
   │          child!, // 直接复用外部传入的 heavyChild 内存指针，零 build 开销！ │
   │        ],                                                                │
   │      );                                                                  │
   │    },                                                                    │
   │ );                                                                       │
   └──────────────────────────────────────────────────────────────────────────┘

1. `child` 属性预缓存的微观物理收益
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 状态变更触发 ``builder`` 闭包重新执行时，传入的 ``child`` 依然是外部已实例化的同一个组件指针；
* 在底层 Element 树比对（``updateChild``）时，框架检测到新旧 Widget 指针完全一致（``identical == true``），**瞬间短路跳过整棵庞大子树的递归构建**，仅对包裹在外部的局部文本节点执行微观重绘。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 07 第 2 节：``07_framework_state_and_gestures/02_listenable_and_changenotifier.rst`` 已全量落盘完工**！
  深度解构了 ``Listenable`` 与 ``ValueListenable`` 抽象契约、``ChangeNotifier`` 定长数组倍增与 50% 滞后收缩算法、递归调用栈深度追踪与延迟缩容、``ValueNotifier`` 身份相等性防抖、以及 ``ListenableBuilder`` 预构建 child 子树隔离机制。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 07 第 3 节：``07_framework_state_and_gestures/03_gesture_arena_hit_test.rst``**。
  我们将深入 ``flutter-3.32.0/packages/flutter/lib/src/gestures/arena.dart`` 与 ``hit_test.dart`` 源码，系统剖析硬件触控点（``PointerEvent``）到命中测试结果树（``HitTestResult``）的遍历收集、单点与多手势竞技场（``GestureArenaManager``）胜负决胜仲裁、手势扫掠（Sweep）与拖拽手势冲突化解机制。
