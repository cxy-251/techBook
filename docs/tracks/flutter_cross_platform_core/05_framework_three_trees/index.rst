========================================================================
模块 05：响应式核心——三棵树拓扑与 Diff 算法 (Three Trees & Diff)
========================================================================

本模块深入 Flutter 3.32 SDK 框架层核心（packages/flutter/lib/src/widgets/framework.dart），系统化剖析 Widget 不可变配置图纸、Element 树的生命周期与内存挂载、updateChild 两级 Diff 算法、GlobalKey 跨父级重挂载原理、以及 BuildOwner 与 BuildScope 深度排序脏节点批量重构机制。

.. toctree::
   :maxdepth: 2

   01_widget_immutable_tree
   02_element_lifecycle_and_mount
   03_diff_algorithm_and_keys
   04_build_owner_dirty_scope
