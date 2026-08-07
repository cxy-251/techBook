第057章：KD-Tree
===============

核心知识点
----------

KD-Tree 是空间划分结构
   内部节点用一个轴对齐 split plane 把当前空间切成两个子区域，叶子保存与该区域重叠的 primitive。它不是先给对象分组再包 bounds，而是先切空间，再决定哪些 primitive 属于哪些区域。

Ray traversal 依赖参数区间和 near/far 顺序
   Ray 与 scene bounds 相交后得到 ``[tMin,tMax]``。内部节点根据 split plane 计算 ``tSplit``，先访问 near child，把 far child 连同参数区间压栈。若 near 路径已经得到更近命中，远处节点可以直接停止访问。

KD-Tree 的优势来自空空间跳过
   静态场景中，好的 split 能把大块空区域切出来，让 primary/shadow ray 只经过少量空间节点。空区域比例高、几何长期不动、查询频繁时，构建成本更容易被长期 traversal 收益摊销。

Primitive 跨 split 会产生复制
   一个长墙或大三角形跨过切分平面时，需要同时进入左右 child 的 primitive list。复制过多会增加内存、叶子测试和 mailboxing 成本，因此 split 质量不仅要减少 child primitive 数，还要控制跨平面重叠。

SAH 是主要高质量 split 模型
   SAH 用 child surface area 估计 ray 进入概率，再结合左右 primitive 数量与 traversal/intersection cost 评估 split。它同时奖励空区域并惩罚 primitive duplication，比最长轴中点或 centroid median 更贴近真实查询成本。

终止条件决定树深与叶子成本
   ``maxDepth``、``maxPrims``、空节点奖励和最小空间尺度共同决定何时停止继续切分。树过深会增加节点和栈，叶子过大则会增加 primitive test。两者必须联合调优。

高效构建依赖预计算 bounds 与连续内存
   Primitive bounds 应在构建前统一计算；split candidate、分类 scratch buffer、节点数组和 leaf primitive index 应尽量避免频繁动态分配。Traversal-friendly layout 通常让 child 相邻、leaf range 连续。

Mailboxing 用来避免重复 primitive test
   同一 primitive 被复制到多个 leaf 后，一条 ray 可能重复遇到它。Mailboxing 通过 ray-local 或 thread-local 记录避免重复测试，但在多线程/GPU 上会增加状态与同步成本，只应在 duplication 足够严重时使用。

KD-Tree 适合静态 ray query、点查询和空空间跳过
   静态 triangle tracing、shadow visibility、点云邻域、photon lookup、固定体素/空间 occupancy 都可受益。频繁移动几何则会让 primitive 重新分类，更新成本显著高于可 refit 的 BVH。

结构选择必须绑定真实查询
   Primary ray 看 front-to-back early-out，shadow ray 看 first blocker，点查询看 node bounds 到查询点的距离，体素查询看 empty-space skipping。不同 query 的最优 split 与叶子阈值可能不同。

关键路径
--------

构建：

::

   primitive bounds
   → current node bounds
   → generate split candidates
   → evaluate midpoint / median / SAH
   → classify primitives
   → crossing primitive enters both children
   → recurse
   → write interior node / leaf range
   → collect node / leaf / reference statistics

Ray traversal：

::

   ray intersects scene bounds
   → current [tMin,tMax]
   → read axis + split
   → compute tSplit
   → visit near child
   → defer far child on stack
   → leaf primitive tests
   → update closest hit / early-out
   → continue only if deferred interval still relevant

性能排查：

::

   build time
   → node / leaf count
   → primitive reference count
   → max depth / average leaf size
   → node visits / primitive tests / P95
   → inspect duplicated long primitives
   → adjust split / maxDepth / maxPrims / mailbox policy

概念辨析
--------

* **KD-Tree 与 BVH**：KD-Tree 划分空间，primitive 可复制；BVH 划分对象集合，通常一个 primitive 只进入一个 child。
* **Median 与 SAH**：median 保持数量平衡；SAH 直接估计未来 ray traversal 成本。
* **空节点与大叶子**：空节点能快速跳过空间；过度追求空节点也会产生深树和额外节点。
* **Primitive duplication 与 mailboxing**：前者来自空间切分，后者只是避免重复测试的补救机制。
* **KD-Tree 与 Uniform Grid**：前者自适应切分、适合非均匀静态空间；后者规则寻址、适合密度相对均匀与动态局部查询。
* **静态优势与动态代价**：KD-Tree 的高 traversal quality 常建立在昂贵构建之上，因此频繁更新是主要边界。

本章结论
--------

KD-Tree 应按“空间切分—primitive 分类—near/far traversal—叶子测试”理解。它的核心价值是让 ray 按空间顺序推进并快速跳过空区域，代价是 split 构建成本和跨平面 primitive 复制。静态、高空空间比例、频繁 ray query 的场景最值得使用；动态场景则通常优先 BVH、两层结构或 grid。判断质量要同时看构建统计、primitive reference 增长和 P95 查询成本。