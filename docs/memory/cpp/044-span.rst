第044章：Span
=============

核心知识点
----------

* ``std::span<T, Extent>`` 是 C++20 的 non-owning contiguous range view，用来表示一段已经存在的连续对象序列。
* ``span`` 不分配、不构造、不销毁元素；它只保存可见范围状态，底层存储仍由 vector、array、原生数组或外部缓冲区拥有。
* 动态长度 ``std::span<T>`` 在对象中保存运行期长度；静态长度 ``std::span<T, N>`` 把长度写入类型。
* ``std::span<T>`` 表示可修改元素，``std::span<const T>`` 表示只读元素；``const std::span<T>`` 只限制 span 对象自身，不会自动把元素变成 const。
* ``span`` 要求底层元素连续，因此适合 vector、array、raw array、C buffer，不适合 list、forward_list 等节点容器。
* ``span`` 适合作为按值函数参数，因为复制的只是视图状态，不复制底层元素。
* ``vector&`` 应用于需要改变 size/capacity 的接口；``span`` 应用于只读取或原地修改既有连续元素的接口。
* raw pointer + length 可以在 C/ABI 边界继续存在，进入 C++ 逻辑后可尽早包装成 ``span`` 统一地址与长度。
* span 的核心风险是悬垂：底层所有者销毁、vector 重分配、缓冲区替换后，旧 span 仍保留旧地址和长度但已失效。
* 把 span 保存为成员等于把外部存储生命周期写进对象不变量；长期拥有数据时应改用拥有式容器或显式共享所有权。

关键路径
--------

1. 先判断函数是否需要拥有、扩容或缩短数据；需要时使用 owning container，而不是 span。
2. 若函数只处理已有连续元素，再判断元素是否需要可修改，选择 ``span<T>`` 或 ``span<const T>``。
3. 判断长度是运行期数据还是接口协议的一部分，选择 dynamic extent 或 static extent。
4. 构造 span 时确认地址与长度对应同一段有效对象序列。
5. 使用期间追踪底层所有者，确认其生命周期覆盖 span 的全部访问。
6. 若底层是 vector，检查 ``push_back``、``reserve``、``resize`` 等操作是否可能重新分配。
7. 当底层存储可能变化时，变化后重新建立 span，不复用旧视图。

概念辨析
--------

* **span 与 vector**：vector 拥有动态存储和容量；span 只观察已有连续存储。
* **span 与 array**：array 拥有固定大小元素；静态 span 只表达当前可见窗口长度，不拥有元素。
* **span 与 pointer + length**：二者都不拥有数据；span 把地址和长度绑定成一个范围对象，并提供标准 range 接口。
* **dynamic extent 与 static extent**：前者长度是运行期状态，后者长度进入类型系统。
* **``span<const T>`` 与 ``const span<T>``**：前者禁止通过视图修改元素，后者只禁止修改 span 对象本身。
* **non-owning 与 borrowed**：span 是 non-owning view；它的安全仍取决于底层对象是否存活。

本章结论
--------

``std::span`` 的正确使用顺序是“所有权 → 连续性 → 可变性 → 长度约束 → 生命周期 → 失效规则”。它最适合表达函数对连续缓冲区的临时访问需求，用类型替代散落的指针与长度，同时保持底层所有权边界清晰。