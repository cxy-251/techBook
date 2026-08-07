第058章：Common STL Mistakes
===========================

核心知识点
----------

* STL 常见错误首先是生命周期错误：iterator、reference、pointer、``string_view``、``span``、ranges view 都只是位置或观察入口，不拥有被观察对象。
* ``vector`` 扩容会搬迁元素，旧 iterator/reference/pointer 全部可能失效；``unordered_map`` rehash 主要使 iterator 失效，未被 erase 的元素 reference/pointer 通常仍可保持。
* 把 ``string_view`` 作为哈希表 key、把 ``Record*`` 指向 ``vector`` 元素、把引用捕获 lambda 存入 ``std::function``，都必须追踪底层所有者寿命和后续结构修改。
* ``std::remove_if`` 只重排区间并返回新的逻辑尾，不改变容器 ``size()``；对 ``vector`` 等容器通常还要执行 ``erase(new_end, end())``，C++20 可优先使用 ``std::erase_if``。
* 排序 comparator 必须满足 strict weak ordering：不可用 ``<=`` 代替严格关系，不应让比较结果依赖调用次数或会变化的外部状态。
* ``std::function`` 提供运行时类型擦除和统一 callable 签名，但可能带来 target 存储、复制、间接调用和优化屏障；热路径优先评估模板参数或具体 lambda 类型。
* 保存观察对象前，必须先确定后续是否会扩容、erase、rehash、移动拥有者、修改字符串缓冲或跨异步边界。

关键路径
--------

保存 iterator/reference/pointer/view → 找到真正拥有者 → 列出后续修改操作 → 查询该操作的失效规则 → 若位置失效则重新获取或改存 key/index/拥有值 → 再检查算法语义与比较器契约 → 最后评估 callable 包装成本。

删除序列元素的标准路径是 ``remove_if`` 负责把保留元素压到前部，返回逻辑尾；容器 ``erase`` 负责销毁尾部对象并缩短 size。两层责任不能混淆。

概念辨析
--------

* **对象仍存在 vs 观察入口仍有效**：view 或 pointer 自身还保存数值，不代表目标对象或存储仍然有效。
* **vector reallocation vs unordered rehash**：前者通常搬迁元素地址；后者重建 bucket 遍历结构，元素节点地址语义与 iterator 失效规则不同。
* **remove vs erase**：算法 ``remove/remove_if`` 改元素排列；容器 ``erase`` 改容器大小和对象生命周期。
* **strict weak ordering vs 普通布尔函数**：排序比较器必须形成稳定的严格弱序，不是任意返回 bool 的函数都合法。
* **lambda vs std::function**：lambda 是具体闭包类型，适合静态优化；``std::function`` 用类型擦除换取运行时统一存储和接口。

本章结论
--------

排查 STL 问题时先看所有权和生命周期，再看容器结构是否重建，再看算法是否真的改变 size，随后检查 comparator 契约和 callable 封装成本。大多数“接口还能调用但结果错误”的问题，都能在这条路径上定位。