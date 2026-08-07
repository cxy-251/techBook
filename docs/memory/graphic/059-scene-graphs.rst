第059章：Scene Graph
===================

核心知识点
----------

Scene Graph 负责表达对象关系，而不是直接替代空间索引
   Node 保存身份、父子层级、local transform、component 和资源引用；world bounds、visibility list、LOD、render queue 则属于后续运行时系统。场景图提供“对象是谁、属于谁、相对谁变换”，空间索引负责“当前查询要考虑哪些对象”。

层级变换的核心关系是 parent world × local
   在常见列向量约定中，``world(child) = world(parent) * local(child)``。父节点必须先于子节点更新。矩阵乘法约定、左右手系、TRS 组合和 shader 约定必须全链一致。

Dirty flag 用来限制变换更新范围
   某个 local transform 改变后，该节点及其所有后代的 world matrix 都失效。只移动 ``Car_Rig`` 时，车身和车轮子树需要更新；只旋转一个轮胎时，其他兄弟节点无需更新。高效实现会用 dirty queue、拓扑顺序数组或分层批处理代替全树递归。

循环依赖必须在 reparent 阶段禁止
   Scene graph 应保持无环树或森林结构。新 parent 不能是当前节点的后代，否则 world transform 出现无限依赖。Reparent 还应明确是否保持 world transform，并同步刷新 dirty、bounds、selection path 和序列化关系。

World matrix 与 world bounds 必须同步更新
   World matrix 服务渲染位置，world bounds 服务空间查询。只更新 matrix 不更新 bounds，会出现物体已移动但仍按旧位置剔除；只更新 bounds 不更新 per-object transform，则会出现剔除正确、画面位置错误。

可扩展场景系统应拆分编辑器层级与高频 runtime 数据
   编辑器需要可读名称和 parent-child 路径；运行时更适合紧凑数组、稳定 handle、TransformComponent、MeshRendererComponent、world bounds cache 和 render item cache。Scene graph 保留组织语义，高频系统按 component/handle 批处理。

Scene Graph 与 ECS 可以组合
   Node 可以持有 entity ID，Transform/Renderer/Light 等数据进入 ECS 或 component registry。编辑器层级仍由 node 表达，runtime 系统按 component 数组批量更新。两者不是互斥架构。

资源引用应与节点身份分离
   Mesh、material、texture、skeleton 等应通过稳定 handle/GUID 引用。多个 node 可以共享同一 mesh/material，资源异步加载时 node 仍可存在，资源 ready 后再生成 render item。

一帧更新应按依赖顺序分阶段
   Script/animation 先写 local transform，transform system 更新 world，bounds system 更新 world bounds，spatial index 接收 dirty object，visibility system 查询 camera，renderer 生成并排序 render items，最后录制 GPU 命令。每阶段都应有明确输入输出。

可见性剔除依赖空间索引，不应遍历整个编辑器树
   Scene graph 可以提供 coarse group bounds，但大型场景应将 renderable bounds 插入 BVH、octree、grid 或其它 spatial index。Camera 查询得到 visibility list 后，再做 LOD、pass filter 和 render queue 排序。

Render Queue 是 Scene Graph 到 GPU 的最终转换层
   Draw item 通常包含 mesh/material handle、pipeline state、world matrix/constant offset、pass、sort key 和 instance data。Scene graph 的树顺序不应直接决定 draw 顺序；不透明、透明、shadow、reflection 等 pass 都有自己的提交规则。

场景组织模式要匹配资产与动态程度
   游戏关卡通常拆 static chunk、dynamic actor、VFX；CAD 更强调装配层级、稳定 ID 和大模型选择；影视资产更强调 rig/shot/prefab 关系；数据可视化更强调 streaming、query 和可见性。共同原则是“逻辑层级保留语义，专门索引服务高频查询”。

关键路径
--------

Transform 更新：

::

   script / animation writes local TRS
   → mark node + descendants dirty
   → parent-first world update
   → world matrix
   → world bounds update
   → spatial index update

Scene 到渲染：

::

   scene node identity
   + world transform
   + resource handles
   → spatial index
   → camera visibility query
   → visibility list
   → LOD / pass filtering
   → render item build
   → render queue sort
   → GPU draw

资源与序列化：

::

   stable node ID / parent ID
   → local transform + components
   → resource GUID / handle
   → load all nodes
   → rebuild hierarchy
   → resolve resources
   → full transform / bounds refresh

对象未显示排查：

::

   local transform
   → world matrix
   → world bounds
   → spatial index membership
   → visibility list
   → LOD / render item
   → mesh/material binding
   → draw call

概念辨析
--------

* **Scene Graph 与 Spatial Index**：前者表达逻辑层级和变换，后者负责高频空间查询。
* **Local Transform 与 World Transform**：local 相对 parent，world 是沿祖先链组合后的最终空间变换。
* **Node 与 Resource**：node 是场景身份；mesh/material 是可共享资产，不应把资源本体复制进每个节点。
* **Scene Graph 与 ECS**：scene graph 提供层级关系，ECS 提供数据批处理和系统调度，可以互补。
* **Visibility List 与 Render Queue**：前者回答“谁可见”，后者回答“以什么 pass 和顺序提交”。
* **Editor Tree 与 Runtime Layout**：可读树适合编辑，紧凑数组适合每帧更新；同一对象可以同时拥有两个视图。
* **Transform Dirty 与 Resource Dirty**：变换失效和资源热更新是不同状态，不能共享一个模糊 dirty 标记。

本章结论
--------

Scene Graph 应按“对象身份—父子层级—local/world transform—world bounds—空间索引—visibility list—render queue”理解。它的核心职责是稳定表达对象归属和变换来源，高频剔除与提交则交给专门系统。遇到画面对象错误时，沿 local、world、bounds、spatial index、visibility、render item 顺序排查，比直接从编辑器树或 draw call 两端猜测更可靠。