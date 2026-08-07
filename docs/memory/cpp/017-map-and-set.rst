第017章：Map and Set
====================

核心知识点
----------

* ``std::map`` 和 ``std::set`` 都维护一个持续有序、key 唯一的关联空间；``map`` 保存 ``Key -> T``，``set`` 保存 ``Key`` 本身。
* 容器的顺序、唯一性和查找方向都由 ``Compare`` 决定，默认通常是 ``std::less<Key>``。
* 两个 key 的“等价”不是依赖 ``operator==``，而是 ``!comp(a,b) && !comp(b,a)``；唯一键容器只允许一个比较器等价类代表。
* 比较器必须形成严格弱序。若使用 ``<=``、状态不稳定或不满足传递性，树搜索和唯一性判断都会失去前提。
* 常见实现使用红黑树等自平衡 BST：容器对象保存根、大小、比较器和 allocator，节点保存父子链接、平衡状态与元素。
* ``set`` 节点的 value 就是 key；``map`` 节点的 value 是 ``std::pair<const Key, T>``。key 为 const 是为了阻止原地改 key 破坏树顺序。
* ``map`` / ``set`` iterator 通常指向树节点并按中序后继 / 前驱移动，因此属于双向迭代器，不支持随机访问。
* 普通插入不会移动已有节点对象；删除只结束目标节点生命周期，因此已有元素的 iterator/reference 在普通插入后保持有效，删除只使被删元素的位置失效。
* ``find``、``lower_bound``、``upper_bound``、``equal_range`` 都复用同一套 comparator + 树搜索模型。
* ``map::operator[]`` 在 key 不存在时会插入节点并值初始化 mapped value，因此“读取”写成 ``[]`` 可能产生修改；只查存在性应使用 ``find`` / ``contains``。
* C++17 node handle 允许 ``extract`` 节点后在容器外修改 key，再重新插入，从而避免在树内直接破坏排序不变量。

关键路径
--------

**唯一键插入**

``key -> Compare 沿树搜索 -> 遇到等价 key：返回已有位置且不插入 -> 未找到：分配/构造节点 -> 链接树 -> 平衡修复 -> 返回 iterator + inserted 状态``。

**find**

``root -> comp(target,current) / comp(current,target) -> 左或右 -> 两边都 false 表示等价 -> 返回节点；走到空节点返回 end``。

**lower_bound / upper_bound**

``lower_bound(k)`` 返回第一个不小于 ``k`` 的节点；``upper_bound(k)`` 返回第一个严格大于 ``k`` 的节点；``equal_range(k)`` 等价于 ``[lower_bound(k), upper_bound(k))``。

**iterator++**

``当前节点有右子树 -> 进入右子树最左节点；否则沿 parent 向上 -> 找到当前节点位于其左子树的第一个祖先``。这就是中序后继。

**operator[]**

``按 key 查找 -> 已存在：返回 second -> 不存在：构造 pair<const Key,T>，其中 T 值初始化 -> 插入节点 -> 返回新节点 second``。

概念辨析
--------

* **排序顺序 vs 插入顺序**：ordered container 的遍历顺序由 comparator 决定，不保留“第几个插入”的业务顺序。
* **等价 vs 相等**：容器唯一性看 comparator 等价，不看 ``operator==``。
* **map key vs mapped value**：key 决定树位置，不能原地改；mapped value 不参与排序，可以修改。
* **ordered vs unordered**：ordered container 提供有序遍历、范围查询、前驱后继；unordered container 更偏向等值查询，不维护全局顺序。
* **节点稳定 vs 连续局部性**：节点式结构提升 iterator/reference 稳定性，同时增加节点指针、独立分配和 cache miss 成本。
* **operator[] vs find/at**：``[]`` 带“缺失则插入”语义；``find`` 只查找；``at`` 要求 key 已存在，否则抛异常。

本章结论
--------

``map`` / ``set`` 的稳定判断模型是：``Compare 定义顺序与等价 -> 自平衡树保存独立节点 -> 按 key 做对数定位 -> 中序 iterator 提供有序遍历 -> 节点式修改维持已有位置稳定``。需要顺序、范围、前驱后继和稳定节点位置时优先考虑 ordered associative container；只需要高频等值查询时再评估 unordered container。