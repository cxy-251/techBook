========================================================================
模块 07：状态分发与手势识别体系 (State & Gestures)
========================================================================

本模块深入 Flutter 3.32 SDK 框架层源码（widgets/ 与 foundation/），剖析 InheritedElement 订阅哈希表在多层级组件树中的存储拓扑与 $O(1)$ 上下文瞬时查找 (framework.dart)、Listenable 与 ChangeNotifier 观察者模式与零冗余内存开销 (change_notifier.dart)、以及 PointerEvent 物理事件从硬件中断输入到 HitTest 树状收集与 GestureArena 手势竞技场仲裁决胜机制 (gestures/)。

.. toctree::
   :maxdepth: 2

   01_inherited_element_hash_table
   02_listenable_and_changenotifier
   03_gesture_arena_hit_test
