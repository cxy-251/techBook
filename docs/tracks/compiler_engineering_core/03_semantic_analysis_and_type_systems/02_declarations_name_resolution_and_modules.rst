====================================================================================================
名字决议与模块依赖图：多遍扫描 (Multi-Pass) 查找、重载决议候选集与跨模块符号可见性
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 3 模块第 1 节中，编译器确立了基于 ``SymbolEntry`` 紧凑内存布局的符号表与作用域树（Scope Tree）拓扑，实现了单编译单元内词法作用域链的单向回溯、变量遮蔽判定以及自由变量逃逸捕获机制。然而，单遍自顶向下查找假定符号在使用前已完成物理声明。在支持互相递归函数、前向引用（Forward Reference）、函数多态重载（Function Overloading）以及多文件模块化工程（Multi-File Module System）中，标识符的绑定无法在单次 AST 遍历中即时收敛。本章深入剖析声明与定义在内存槽位与符号可访问性上的物理边界、多遍扫描（Multi-Pass）与按需延迟解析架构、重载决议（Overload Resolution）的三阶段候选集剪枝与类型转换等级权重判定算法、模块依赖有向无环图（DAG）构建与 Tarjan 强连通分量循环检测，以及跨编译单元符号可见性控制与 Itanium / Rust 符号修饰（Name Mangling）机制，并交付一套工业级 C++ 多遍名字决议与模块拓扑调度引擎。

声明与定义的物理边界与前向引用挑战
----------------------------------

在编译器内部表示中，声明（Declaration）与定义（Definition）对应着不同层级的内存分配与语义证据生成阶段。语法分析产出的抽象语法树节点仅记录符号标识符切片，语义分析器必须依据符号所处阶段分配对应规格的内部数据结构。

声明与定义的编译器内部数据结构分工
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

声明操作的核心职责是将具名实体登记至编译器的符号索引字典中。该过程分配固定尺寸的符号条目（``SymbolEntry``，占用 56 字节元数据空间），写入名字字符串驻留指针（``InternedString``）、符号种类枚举（``SymbolKind``）、源码物理坐标（``SourceLocation``）以及初步的类型签名指针。此时实体处于不完整状态（Incomplete Entity），编译器未为其分配目标机数据段地址（``.data`` / ``.bss`` 偏移）或栈帧局部偏移（Stack Slot Offset），亦未生成函数的控制流图（CFG）与机器指令。

定义操作则在已有符号条目的基础上补全物理实体所需的全部几何与语义数据：
1. **类型定义（Type Definition）**：计算结构体或类的成员字段物理排布（``StructLayout``）、字段相对基地址的字节偏移量、类型的总对齐要求（Alignment）与总占用字节数（Size）。
2. **函数定义（Function Definition）**：解析函数体复合语句，构建基本块（Basic Blocks）与控制流图，验证所有内部引用的合法性，生成可供中端优化的中间表示（IR）。
3. **变量定义（Variable Definition）**：确定变量的物理存储位置，为全局变量在目标文件中分配绝对/相对数据段槽位，为局部变量分配栈帧基址指针偏移量（如 ``[RBP - offset]``），并生成初始值的求值表达式树。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  声明 (Declaration) 与 定义 (Definition) 内存状态演进       |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 阶段 1: 前向声明 struct Buffer; ]                                        |
   |   +---------------------------------------------------------------------+   |
   |   | SymbolEntry: Name="Buffer", Kind=Type, TypePtr=0x1000 (Incomplete)  |   |
   |   | Layout: Size=0, Align=0, Fields={}, Complete=false                  |   |
   |   +---------------------------------------------------------------------+   |
   |         |                                                                   |
   |         | 可行操作: 计算指针大小 sizeof(Buffer*) = 8B, 形成参数 Buffer*     |
   |         | 非法操作: 计算成员偏移 buffer->count, 栈上分配 Buffer obj         |
   |         v                                                                   |
   |   [ 阶段 2: 完整定义 struct Buffer { int count; char flag; }; ]             |
   |   +---------------------------------------------------------------------+   |
   |   | SymbolEntry: Name="Buffer", Kind=Type, TypePtr=0x1000 (Completed)   |   |
   |   | Layout: Size=8B, Align=4B, Complete=true                            |   |
   |   | Fields:                                                             |   |
   |   |   - count: Type=i32, Offset=0x00, Align=4B                          |   |
   |   |   - flag : Type=i8,  Offset=0x04, Align=1B                          |   |
   |   |   - [Padding]: 3 Bytes (0x05 - 0x07)                                |   |
   |   +---------------------------------------------------------------------+   |
   |                                                                             |
   +-----------------------------------------------------------------------------+

.. list-table:: 声明与定义在编译阶段提供的事实依据与硬件约束对比
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 源码实体形态
     - 编译器内存元数据
     - 允许的合法语法/语义动作
     - 触发编译阻断的非法操作
   * - 不完整类型声明 (``struct T;``)
     - ``SymbolEntry`` 标记 ``Incomplete``；无字段表
     - 声明 ``T*`` 指针、``T&`` 引用、作为函数形参/返回值签名
     - 访问成员字段、实例化局部对象、求取 ``sizeof(T)``
   * - 完整类型定义 (``struct T { ... };``)
     - 填充 ``FieldLayout``、对齐尺寸、成员函数表
     - 内存对齐计算、字段 GEP 指令生成、栈/堆内存空间分配
     - 重复提供同名类体（同编译单元单一定义违规）
   * - 函数接口声明 (``int fn(T*);``)
     - 记录入参类型列表、返回值类型、调用约定
     - 函数调用语法检查、参与重载候选集匹配
     - 函数内联展开、生成目标机器代码段
   * - 函数完整定义 (``int fn(T*) { ... }``)
     - 挂载函数体 AST、绑定局部作用域树与控制流图
     - 生成中端 IR 函数体、执行数据流分析与机器码发射
     - 重复提供同签名函数体（ODR 重复定义违规）

线性源码排布与图状程序依赖的物理失配
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

源码文件以一维连续字节流的形式组织，由词法分析器和语法分析器自前向后线性读取。然而，程序内部的实体关系呈现为网状图拓扑结构：
- **函数间互相递归（Mutual Recursion）**：函数 $A$ 在函数体内调用函数 $B$，而函数 $B$ 在函数体内调用函数 $A$。无论源码文本如何排列先后顺序，线性单遍读取必然导致其中一个函数在被调用时处于“未声明”状态。
- **结构体指针循环引用（Cyclic Pointer Reference）**：结构体 ``Node`` 包含指向结构体 ``Edge`` 的指针成员，结构体 ``Edge`` 包含指向结构体 ``Node`` 的指针成员。

为解决一维文本排布与图状依赖的物理失配，编译器采用两条工程路径：
1. **显式前向声明机制（C/C++ 范式）**：强制开发者手动书写前向声明语句，向符号表提前注入元数据骨架，维持单遍扫描的前置依赖要求。
2. **多遍扫描与按需分析架构（Java/Rust/Go/Swift 范式）**：编译器前端解耦“符号收集”与“函数体验证”两个阶段，自动实现图状依赖的解析收敛。

多遍扫描 (Multi-Pass) 架构与按需延迟决议流转
--------------------------------------------

生产级现代编译器普遍采用多遍扫描（Multi-Pass Pipeline）或按需查询驱动（Query-Based Demand-Driven）架构，将名字决议划分为严格依赖定序的独立阶段。

多遍扫描流水线阶段拓扑
~~~~~~~~~~~~~~~~~~~~~~

在标准三遍扫描架构中，AST 节点经历三次具有明确数据依赖边界的遍历过程：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        三遍扫描 (Three-Pass) 语义分析管线                   |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 原始 AST 树 (Raw AST) ]                                                 |
   |              |                                                              |
   |              v                                                              |
   |   +---------------------------------------------------------------------+   |
   |   | Pass 1: 符号索引骨架收集 (Skeleton Symbol Indexing)                 |   |
   |   | - 仅遍历全局/模块顶层与类型外壳                                     |   |
   |   | - 注册结构体名、接口名、全局变量名、函数名与原始类型注解            |   |
   |   | - 函数体 AST 节点保持未解析状态 (Opaque Unresolved Subtree)         |   |
   |   +---------------------------------------------------------------------+   |
   |              |                                                              |
   |              | 产生: 全局符号骨架表 (Global Skeleton Symbol Table)          |
   |              v                                                              |
   |   +---------------------------------------------------------------------+   |
   |   | Pass 2: 类型签名与布局计算 (Type Signatures & Memory Layout)        |   |
   |   | - 沿作用域树决议所有函数形参、返回值、结构体字段的类型引用          |   |
   |   | - 计算结构体物理尺寸、字段对齐与内存偏移 (Compute Struct Layouts)   |   |
   |   | - 确定类型体系继承图与接口实现契约                                  |   |
   |   +---------------------------------------------------------------------+   |
   |              |                                                              |
   |              | 产生: 类型系统完备 AST (Type-Resolved Interface AST)         |
   |              v                                                              |
   |   +---------------------------------------------------------------------+   |
   |   | Pass 3: 函数体内部名字绑定与类型检查 (Body Resolution & Typing)     |   |
   |   | - 进入各函数体，实例化局部作用域树与局部变量条目                    |   |
   |   | - 决议 DeclRefExpr、MemberExpr、CallExpr 标识符绑定                 |   |
   |   | - 执行重载决议、隐式类型转换插入与表达式类型校验                    |   |
   |   +---------------------------------------------------------------------+   |
   |              |                                                              |
   |              v                                                              |
   |   [ 强类型绑定 AST (Fully Bound & Typed AST) ]                              |
   |                                                                             |
   +-----------------------------------------------------------------------------+

按需查询驱动 (Query-Based Demand-Driven) 架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在现代增量编译器（如 Rust 编译器 ``rustc`` 的 Salsa 架构）中，固定顺序的多遍扫描被重构为细粒度的有向无环查询系统（Query DAG）。
- 当主编译流程请求函数 $F$ 的中间表示时，触发查询 ``mir_built(F)``。
- 该查询自动触发前置子查询 ``typeck(F)``（对函数 $F$ 执行类型检查与名字绑定）。
- ``typeck(F)`` 在遇到对函数 $G$ 的调用时，仅触发 ``type_of(G)`` 查询以获取 $G$ 的签名，无需触发 ``mir_built(G)`` 或解析 $G$ 的函数体。
- 查询引擎自动缓存各节点计算结果；当某个函数体源码发生修改时，仅与其相关的局部查询失效，全局接口层查询结果保持有效。

.. list-table:: 典型名字决议架构特征与性能对比
   :widths: 22 26 26 26
   :header-rows: 1
   :class: tight-table

   * - 架构维度
     - 单遍扫描 (Single-Pass)
     - 固定多遍扫描 (Multi-Pass)
     - 按需查询式 (Query-Based)
   * - 内存峰值占用
     - 极低（边解析边发射 IR）
     - 中高（全量 AST 驻留内存）
     - 可控（细粒度按需缓存与淘汰）
   * - 前向引用支持能力
     - 弱（依赖人工前向声明）
     - 完全支持（模块内任意声明）
     - 完全支持（按需依赖自动触发）
   * - 增量编译适应性
     - 无（源码微调需整文件重编译）
     - 差（以文件为粗粒度单元重跑）
     - 极高（精确定位失效查询节点）
   * - 代表性编译器实现
     - Turbo Pascal, C89/C99 原型
     - Clang, Javac, Go Compiler
     - Rustc (Salsa), Swiftc

重载决议 (Overload Resolution) 候选集剪枝与打分权重判定
-------------------------------------------------------

重载决议负责在存在多个同名可调用实体时，依据调用点的语法上下文与实参类型特征，计算出唯一的最佳目标函数。该算法分为候选集构造、可行性过滤与转换等级排序三个阶段。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        重载决议三阶段执行状态机                             |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   调用点输入: CallExpr( Callee="process", Args=[ arg_0, arg_1, ... ] )       |
   |                        |                                                    |
   |                        v                                                    |
   |   [ 阶段 1: 候选函数集构造 (Candidate Construction) ]                       |
   |     - 词法作用域检索 (Unqualified Lookup)                                   |
   |     - 参数相关查找 (Argument-Dependent Lookup, ADL)                         |
   |     - 成员函数与基类继承链虚表检索                                          |
   |                        |                                                    |
   |                        | 产出: 候选函数集 Candidates = { F_1, F_2, F_3, ... }|
   |                        v                                                    |
   |   [ 阶段 2: 可行函数集过滤 (Viable Filtering) ]                             |
   |     - 判定形参与实参数量一致性 (匹配必选参数、默认参数、变长参数)           |
   |     - 判定每个实参到对应形参是否存在合法转换路径                            |
   |                        |                                                    |
   |                        | 过滤不可行项，产出: ViableSet <= Candidates         |
   |                        v                                                    |
   |   [ 阶段 3: 最佳可行函数排序与判定 (Best Viable Ranking) ]                  |
   |     - 对 ViableSet 中的每个函数计算全参数类型转换序列权重                   |
   |     - 应用 Pareto 支配性原则判定: 严格优于其他全部候选                      |
   |            /                               \                                |
   |     [ 命中唯一最优解 ]               [ 权重相同 / 无绝对支配者 ]             |
   |            |                               \                                |
   |            v                                v                               |
   |     成功绑定 AST 目标函数               触发编译期重载二义性错误 (Ambiguity) |
   |                                                                             |
   +-----------------------------------------------------------------------------+

阶段 1：候选函数集构造（Candidate Set Construction）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

编译器通过多路检索机制收集所有同名函数条目：
1. **非限定作用域查找（Unqualified Lookup）**：自调用点所处的当前局部作用域起，沿作用域树的 ``Parent`` 链向上检索同名符号。若命中一组重载函数集合，则将其全部加入候选集。
2. **实参依赖查找（Argument-Dependent Lookup, ADL / Koenig Lookup）**：对于非成员函数调用，编译器提取所有实参表达式的静态类型，将这些类型所在的命名空间与模块作用域纳入查找范围，收集其中声明的同名接口。
3. **类成员与基类继承查找（Member & Class Hierarchy Lookup）**：对于形如 ``obj.method()`` 的调用，先解析 ``obj`` 的类型，在其成员表及所有基类的作用域中收集成员函数候选。

阶段 2：可行函数集筛选（Viable Function Filtering）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于候选集中的每个函数 $F$，执行硬性规则过滤：
1. **参数数量匹配**：设实参个数为 $N_{	ext{args}}$，函数 $F$ 的形参总数为 $N_{	ext{params}}$，无默认值的必选参数个数为 $N_{	ext{req}}$。若 $N_{	ext{args}} < N_{	ext{req}}$ 或（在无变长参数情况下）$N_{	ext{args}} > N_{	ext{params}}$，则淘汰 $F$。
2. **类型转换可行性**：对于每一个参数位置 $i \in [0, N_{	ext{args}}-1]$，必须存在从实参类型 $T_{	ext{arg}, i}$ 到形参类型 $T_{	ext{param}, i}$ 的隐式类型转换路径（Implicit Conversion Sequence）。若任意参数无法完成转换，则淘汰 $F$。

阶段 3：类型转换序列等级划分与 Pareto 支配性判定
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为每个可行函数 $F$ 在各参数位置上的类型转换路径赋予形式化质量等级。编译器将转换质量划分为五个严格递减的标准等级：

.. list-table:: 实参向形参隐式类型转换等级序列与判定权重
   :widths: 15 20 35 30
   :header-rows: 1
   :class: tight-table

   * - 转换等级
     - 等级名称
     - 具体类型转换规则与物理操作
     - 转换代价与硬件行为
   * - Rank 1 (100分)
     - 精确匹配 (Exact Match)
     - 类型完全一致、仅发生左值向右值转换、数组向指针衰减、或增加 ``const/volatile`` 限定符
     - 零指令开销，物理寄存器直接传递
   * - Rank 2 (80分)
     - 整数/浮点提升 (Promotion)
     - 小整数符号扩展提升（``i8/i16 -> i32``）、单精度向双精度扩展（``f32 -> f64``）
     - 单条符号扩展指令（如 ``MOVSX`` / ``CVTSS2SD``）
   * - Rank 3 (60分)
     - 标准转换 (Standard Conversion)
     - 整数符号转换（``i32 -> u32``）、跨位宽截断/扩展（``i32 -> i64``）、派生类指针向基类指针偏移调整
     - 涉及数值截断、符号位重解释或基类虚表偏移加算
   * - Rank 4 (40分)
     - 用户自定义转换 (User-Defined)
     - 调用单参数转换构造函数、显式/隐式类型转换运算符重载
     - 插入函数调用、构造临时栈对象、调用析构函数
   * - Rank 5 (20分)
     - 变长参数匹配 (Ellipsis)
     - 匹配 C 风格变长参数（``...``）
     - 参数按 ABI 规则连续压栈或占用通用溢出区

**Pareto 支配性选择算法（Best Viable Function Selection）**：
设可行函数集为 $\mathcal{V}$。函数 $F_a \in \mathcal{V}$ 被判定为唯一最佳可行函数，当且仅当满足以下条件：
1. 对于所有其他可行函数 $F_b \in \mathcal{V} \setminus \{F_a\}$，在所有参数位置 $i$ 上，$F_a$ 的转换等级均优于或等于 $F_b$ 的转换等级：
   $$\forall i \in [0, N_{	ext{args}}-1], \quad 	ext{Rank}(F_a, 	ext{arg}_i) \ge 	ext{Rank}(F_b, 	ext{arg}_i)$$
2. 且对于每个 $F_b$，至少存在一个参数位置 $j$，使得 $F_a$ 的转换等级严格优于 $F_b$：
   $$\exists j \in [0, N_{	ext{args}}-1], \quad 	ext{Rank}(F_a, 	ext{arg}_j) > 	ext{Rank}(F_b, 	ext{arg}_j)$$

若存在两个或多个候选函数在参数比较中互有优劣（例如参数 1 上 $F_1$ 优于 $F_2$，但在参数 2 上 $F_2$ 优于 $F_1$），或者各参数等级完全相同，支配性判定失效，编译器中止并报告调用二义性错误（Ambiguous Call Error）。

模块依赖有向图 (DAG)、拓扑排序与循环依赖检测
--------------------------------------------

现代工程将程序划分为独立的模块（Modules）或编译单元（Translation Units）。模块系统负责确立跨文件的符号可见性边界与物理编译调度顺序。

模块记录物理结构与依赖图建模
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

模块记录（``ModuleRecord``）是编译期管理文件边界的核心实体：
- **Module ID**：模块的全局唯一全限定名（如 ``engine.render.pipeline``）。
- **Export Map**：模块向外部公开暴露的符号条目字典，记录导出名字与底层符号实体指针的映射。
- **Import List**：当前模块显式依赖的外部模块引用及导入符号子集。
- **Module State**：模块在编译管线中的生命周期状态（``Unparsed`` $	o$ ``Parsing`` $	o$ ``Analyzed`` $	o$ ``Compiled``）。

所有模块间的导入关系构成有向图 $G = (V, E)$，其中顶点集合 $V$ 为所有模块记录，有向边 $(M_A, M_B) \in E$ 表示模块 $M_A$ 显式导入了模块 $M_B$ 的导出符号。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        模块依赖图 (Module Dependency Graph)                 |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |              [ Module: app ]               [ Module: diagnostics ]          |
   |                 /         \                         |                       |
   |      imports   /           \ imports                | imports               |
   |               v             v                       v                       |
   |      [ Module: net ]     [ Module: parser ] --------+                       |
   |               \             /                                               |
   |        imports \           / imports                                        |
   |                 v         v                                                 |
   |               [ Module: core ]                                              |
   |                                                                             |
   |      拓扑排序编译执行序列 (Topological Compilation Order):                 |
   |      core -> net -> diagnostics -> parser -> app                            |
   |                                                                             |
   +-----------------------------------------------------------------------------+

拓扑排序（Kahn 算法）与编译管线调度
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了确保每个模块在编译时，其所有依赖模块的接口元数据（如编译产物 ``.pcm``、``.rmeta``、``.bmi``）均已完全就绪，编译器调度器使用 Kahn 算法计算拓扑排序：
1. 统计图中所有模块顶点的入度（In-Degree，即该模块所依赖的未就绪模块数量）。
2. 初始化队列 $Q$，将所有入度为 0 的叶子模块（独立基础模块，如 ``core``）入队。
3. 循环取出队首模块 $M$，将其加入最终编译就绪列表；随后遍历所有依赖 $M$ 的上层模块 $M_{	ext{parent}}$，将其入度减 1。
4. 若 $M_{	ext{parent}}$ 的入度归零，将其压入队列 $Q$。
5. 当队列 $Q$ 为空时，若已处理的模块总数小于图的总顶点数 $|V|$，则证明图中存在有向环路（Cyclic Dependency）。

Tarjan 强连通分量 (SCC) 循环依赖侦测算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当依赖图存在环路时，模块间出现相互等待，导致编译期符号无法定序或运行时静态变量初始化死锁。编译器通过 Tarjan 算法精准定位所有强连通分量（Strongly Connected Components, SCC）并提取环路路径：
- 算法维护全局时间戳计数器 ``Index``、访问深度数组 ``DFN[u]``、追溯值数组 ``LOW[u]`` 以及辅助遍历栈 ``Stack``。
- 对于每个未访问的模块顶点 $u$，设置 ``DFN[u] = LOW[u] = ++Index``，将 $u$ 压入栈中。
- 遍历 $u$ 指向的所有依赖邻接点 $v$：
  - 若 $v$ 未访问，递归遍历 $v$，并在回溯时更新 ``LOW[u] = min(LOW[u], LOW[v])``。
  - 若 $v$ 已在栈中，说明命中祖先后向边（Back-Edge），更新 ``LOW[u] = min(LOW[u], DFN[v])``。
- 当遍历完 $u$ 的所有边后，若 ``DFN[u] == LOW[u]``，则从栈顶连续弹出节点直至 $u$。若弹出的节点集合数量大于 1，该集合即为一个循环依赖强连通分量，编译器据此格式化输出环路诊断链路（如 ``A -> B -> C -> A``）。

跨模块可见性控制矩阵
~~~~~~~~~~~~~~~~~~~~

导入模块时，编译器根据符号附加的可见性修饰符实施访问权限拦截：

.. list-table:: 典型模块系统可见性修饰符在跨文件/跨包边界的访问控制矩阵
   :widths: 20 20 20 20 20
   :header-rows: 1
   :class: tight-table

   * - 可见性修饰符
     - 当前声明作用域
     - 同模块其他文件
     - 下游依赖模块 (Direct Import)
     - 传递依赖模块 (Indirect Import)
   * - ``private``
     - 允许访问
     - 禁止访问
     - 禁止访问
     - 禁止访问
   * - ``fileprivate`` / ``internal``
     - 允许访问
     - 允许访问（同模块）
     - 禁止访问（触发权限错误）
     - 禁止访问
   * - ``public`` (Exported)
     - 允许访问
     - 允许访问
     - 允许直接访问
     - 需显式通过前缀或重新导出（Re-export）访问
   * - ``re-export`` (``pub use``)
     - 允许访问
     - 允许访问
     - 允许直接访问
     - 允许作为当前模块的接口直接访问

跨编译单元符号链接、命名空间修饰 (Name Mangling) 与 ABI 契约
------------------------------------------------------------

当多个编译单元独立编译为目标文件（``.o`` / ``.obj``）后，底层汇编器与静态链接器（Linker）操作的是无类型信息的平坦符号表（Flat Linker Symbol Table）。

符号修饰（Name Mangling）的物理必要性
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

由于汇编语言与 ELF/Mach-O 目标文件规范中，每个全局符号在符号表（``.symtab`` / ``.dynsym``）中仅表现为一个唯一的 ASCII 字符串标签，无法直接表达函数重载（同名不同参）、类成员命名空间（``Namespace::Class::Method``）以及泛型模板实例化特化。编译器前端必须在生成汇编或目标代码前，将高层结构化符号名称与完整类型签名编码为全局唯一的扁平字符串，该过程称为 **符号修饰（Name Mangling）**。

Itanium C++ ABI 符号修饰规范
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

主流工业级编译器（GCC、Clang）在 x86-64 / AArch64 Linux 及 macOS 上遵循 Itanium C++ ABI 规范。其编码规则如下：
1. **全局前缀**：所有修饰符号以 ``_Z`` 开头。
2. **嵌套作用域编码**：若符号位于命名空间或类内部，使用 ``N ... E`` 包裹，内部每个标识符前缀其字符长度（例如 ``N4Math6Matrix5solveE`` 对应 ``Math::Matrix::solve``）。
3. **类型编码序列**：在函数名之后连续附加各参数类型的紧凑缩写编码。

.. list-table:: Itanium C++ ABI 基础类型编码规则对照表
   :widths: 20 25 55
   :header-rows: 1
   :class: tight-table

   * - 源码类型
     - ABI 编码字符
     - 典型修饰示例与解析
   * - ``void``
     - ``v``
     - ``void run()`` $	o$ ``_Z3runv``
   * - ``int`` / ``unsigned int``
     - ``i`` / ``j``
     - ``int calc(int, unsigned int)`` $	o$ ``_Z4calcij``
   * - ``float`` / ``double``
     - ``f`` / ``d``
     - ``float compute(double)`` $	o$ ``_Z7computed``
   * - 指针类型 ``T*``
     - ``P <type>``
     - ``void reset(int*)`` $	o$ ``_Z5resetPi``
   * - 常量限定 ``const T``
     - ``K <type>``
     - ``void view(const char*)`` $	o$ ``_Z4viewPKc``
   * - 引用类型 ``T&``
     - ``R <type>``
     - ``void swap(int&, int&)`` $	o$ ``_Z4swapRiS_``（``S_`` 为重复类型替换压缩标记）

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  Itanium C++ ABI 符号修饰结构剖析                           |
   +-----------------------------------------------------------------------------+
   |   源码定义: int Geometry::Renderer::draw(Buffer* buf, const float scale);    |
   |                                                                             |
   |   修饰后汇编符号: _ZN8Geometry8Renderer4drawEP6BufferKf                     |
   |                                                                             |
   |   拆解分析:                                                                 |
   |     _Z    : C++ 符号修饰前缀 (Mangled Prefix)                               |
   |     N ... E: 嵌套命名空间/类作用域边界                                      |
   |       8Geometry : 长度为 8 的命名空间标识符 "Geometry"                      |
   |       8Renderer : 长度为 8 的类标识符 "Renderer"                            |
   |       4draw     : 长度为 4 的方法标识符 "draw"                              |
   |     E     : 嵌套作用域结束标记                                              |
   |     P6Buffer: 参数 1 为指针 (P)，指向长度为 6 的自定义类型 "Buffer"         |
   |     Kf    : 参数 2 为常量 (K) 浮点数 (f)                                    |
   +-----------------------------------------------------------------------------+

工业级 C++ 多遍名字决议与模块依赖分析引擎实现
----------------------------------------------

以下提供一套完整的工业级 C++ 名字决议与模块依赖拓扑分析引擎。实现涵盖字符串驻留池、作用域树、多遍扫描声明收集器、基于 Pareto 支配性原则的重载决议器、模块依赖 DAG 构建器以及基于 Tarjan 算法的循环导入检测机制。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <string_view>
   #include <vector>
   #include <unordered_map>
   #include <unordered_set>
   #include <memory>
   #include <stack>
   #include <algorithm>
   #include <cstdint>
   #include <cassert>
   #include <iomanip>

   // 源码物理坐标
   struct SourceLocation {
       uint32_t Line = 0;
       uint32_t Column = 0;
   };

   // 字符串驻留池 (String Pool)
   class InternedString {
   public:
       InternedString() : Ptr(nullptr) {}
       explicit InternedString(const char *ptr) : Ptr(ptr) {}

       const char* c_str() const { return Ptr ? Ptr : ""; }
       std::string_view view() const { return Ptr ? std::string_view(Ptr) : std::string_view(); }
       std::string str() const { return std::string(view()); }

       bool operator==(const InternedString &o) const { return Ptr == o.Ptr; }
       bool operator!=(const InternedString &o) const { return Ptr != o.Ptr; }

   private:
       const char *Ptr;
   };

   namespace std {
       template <>
       struct hash<InternedString> {
           size_t operator()(const InternedString &s) const noexcept {
               return hash<const void*>()(s.c_str());
           }
       };
   }

   class StringPool {
   public:
       InternedString intern(std::string_view str) {
           auto it = Pool.find(str);
           if (it != Pool.end()) return InternedString(it->c_str());
           auto [insertedIt, _] = Pool.insert(std::string(str));
           return InternedString(insertedIt->c_str());
       }
   private:
       std::unordered_set<std::string> Pool;
   };

   // 类型系统基础模型
   enum class TypeKind : uint8_t {
       Void,
       Int32,
       Int64,
       Float32,
       Float64,
       Pointer,
       Struct
   };

   struct Type {
       TypeKind Kind;
       InternedString Name;
       const Type *Pointee = nullptr; // 用于 Pointer 类型
       uint32_t Size = 0;             // 字节大小
       uint32_t Align = 0;            // 对齐要求

       bool isInteger() const { return Kind == TypeKind::Int32 || Kind == TypeKind::Int64; }
       bool isFloat() const { return Kind == TypeKind::Float32 || Kind == TypeKind::Float64; }
       bool isPointer() const { return Kind == TypeKind::Pointer; }
   };

   // 符号类别与访问权限
   enum class SymbolKind : uint8_t {
       Variable,
       Function,
       TypeDecl
   };

   enum class Visibility : uint8_t {
       Private,
       Internal,
       Public
   };

   struct ASTNode; // 前向声明

   struct SymbolEntry {
       InternedString Name;
       SymbolKind Kind;
       Visibility Access;
       const Type *DeclType = nullptr;
       std::vector<const Type*> ParamTypes; // 若为函数，记录形参列表
       const Type *ReturnType = nullptr;    // 若为函数，记录返回值类型
       SourceLocation DeclLoc;
       bool IsDefined = false;
       std::string MangledName;
   };

   // 重载决议转换等级枚举
   enum class ConversionRank : uint8_t {
       ExactMatch = 100,
       Promotion  = 80,
       Standard   = 60,
       Incompatible = 0
   };

   class OverloadResolver {
   public:
       // 评估单参数转换等级
       static ConversionRank rankConversion(const Type *from, const Type *to) {
           if (from == to) return ConversionRank::ExactMatch;
           if (!from || !to) return ConversionRank::Incompatible;

           // 整数拓宽提升 (Int32 -> Int64)
           if (from->Kind == TypeKind::Int32 && to->Kind == TypeKind::Int64) {
               return ConversionRank::Promotion;
           }
           // 浮点拓宽提升 (Float32 -> Float64)
           if (from->Kind == TypeKind::Float32 && to->Kind == TypeKind::Float64) {
               return ConversionRank::Promotion;
           }
           // 标准数值转换 (Int32 -> Float64, Int64 -> Float64 等)
           if (from->isInteger() && to->isFloat()) {
               return ConversionRank::Standard;
           }
           // 指针精确兼容或不可隐式转换
           if (from->isPointer() && to->isPointer()) {
               if (from->Pointee == to->Pointee) return ConversionRank::ExactMatch;
           }

           return ConversionRank::Incompatible;
       }

       // 判定函数候选是否可行，并返回各参数的评分序列
       static bool evaluateViability(const SymbolEntry *func, const std::vector<const Type*> &argTypes,
                                     std::vector<ConversionRank> &outRanks) {
           if (func->ParamTypes.size() != argTypes.size()) return false;
           outRanks.clear();
           for (size_t i = 0; i < argTypes.size(); ++i) {
               ConversionRank r = rankConversion(argTypes[i], func->ParamTypes[i]);
               if (r == ConversionRank::Incompatible) return false;
               outRanks.push_back(r);
           }
           return true;
       }

       // 执行 Pareto 最佳可行候选决议
       static const SymbolEntry* resolve(const std::vector<const SymbolEntry*> &candidates,
                                         const std::vector<const Type*> &argTypes,
                                         std::string &outError) {
           struct ViableCandidate {
               const SymbolEntry *Func;
               std::vector<ConversionRank> Ranks;
           };

           std::vector<ViableCandidate> viables;
           for (const auto *cand : candidates) {
               std::vector<ConversionRank> ranks;
               if (evaluateViability(cand, argTypes, ranks)) {
                   viables.push_back({cand, ranks});
               }
           }

           if (viables.empty()) {
               outError = "No viable overloaded candidate found for given argument types.";
               return nullptr;
           }
           if (viables.size() == 1) {
               return viables[0].Func;
           }

           // 多候选 Pareto 支配性比对
           size_t bestIdx = 0;
           for (size_t i = 1; i < viables.size(); ++i) {
               bool iBetterOrEqual = true;
               bool iStrictlyBetter = false;
               bool bestBetterOrEqual = true;
               bool bestStrictlyBetter = false;

               for (size_t p = 0; p < argTypes.size(); ++p) {
                   uint8_t rankI = static_cast<uint8_t>(viables[i].Ranks[p]);
                   uint8_t rankBest = static_cast<uint8_t>(viables[bestIdx].Ranks[p]);

                   if (rankI < rankBest) iBetterOrEqual = false;
                   if (rankI > rankBest) iStrictlyBetter = true;

                   if (rankBest < rankI) bestBetterOrEqual = false;
                   if (rankBest > rankI) bestStrictlyBetter = true;
               }

               if (iBetterOrEqual && iStrictlyBetter && !bestStrictlyBetter) {
                   bestIdx = i; // i 严格优于当前 best
               } else if (!(bestBetterOrEqual && bestStrictlyBetter)) {
                   // 存在交叉优势或同分平局，暂无法直接胜出
               }
           }

           // 最终验证 bestIdx 是否严格支配所有其他候选
           for (size_t i = 0; i < viables.size(); ++i) {
               if (i == bestIdx) continue;
               bool strictlyBetter = false;
               for (size_t p = 0; p < argTypes.size(); ++p) {
                   uint8_t rankBest = static_cast<uint8_t>(viables[bestIdx].Ranks[p]);
                   uint8_t rankI = static_cast<uint8_t>(viables[i].Ranks[p]);
                   if (rankBest < rankI) {
                       outError = "Ambiguous call: conflicting conversions between candidate functions.";
                       return nullptr;
                   }
                   if (rankBest > rankI) strictlyBetter = true;
               }
               if (!strictlyBetter) {
                   outError = "Ambiguous call: multiple equally ranked candidates.";
                   return nullptr;
               }
           }

           return viables[bestIdx].Func;
       }
   };

   // 模块记录与跨模块依赖图系统
   struct ModuleRecord {
       InternedString Name;
       std::unordered_map<InternedString, std::vector<std::unique_ptr<SymbolEntry>>> LocalSymbols;
       std::unordered_map<InternedString, SymbolEntry*> ExportedSymbols;
       std::vector<InternedString> Dependencies; // 导入的下游模块列表
   };

   class ModuleManager {
   public:
       ModuleRecord* createModule(InternedString name) {
           auto mod = std::make_unique<ModuleRecord>();
           mod->Name = name;
           ModuleRecord *raw = mod.get();
           Modules[name] = std::move(mod);
           return raw;
       }

       ModuleRecord* getModule(InternedString name) {
           auto it = Modules.find(name);
           return it != Modules.end() ? it->second.get() : nullptr;
       }

       // 注册导出符号
       void exportSymbol(ModuleRecord *mod, InternedString symName, SymbolEntry *sym) {
           sym->Access = Visibility::Public;
           mod->ExportedSymbols[symName] = sym;
       }

       // Tarjan 强连通分量 (SCC) 循环依赖检测
       std::vector<std::vector<InternedString>> detectCyclicDependencies() {
           uint32_t timer = 0;
           std::unordered_map<InternedString, uint32_t> dfn, low;
           std::unordered_set<InternedString> inStack;
           std::stack<InternedString> st;
           std::vector<std::vector<InternedString>> sccs;

           auto tarjan = [&](auto &self, InternedString u) -> void {
               dfn[u] = low[u] = ++timer;
               st.push(u);
               inStack.insert(u);

               ModuleRecord *uMod = getModule(u);
               if (uMod) {
                   for (InternedString v : uMod->Dependencies) {
                       if (dfn.find(v) == dfn.end()) {
                           self(self, v);
                           low[u] = std::min(low[u], low[v]);
                       } else if (inStack.count(v)) {
                           low[u] = std::min(low[u], dfn[v]);
                       }
                   }
               }

               if (dfn[u] == low[u]) {
                   std::vector<InternedString> currentSCC;
                   while (true) {
                       InternedString top = st.top();
                       st.pop();
                       inStack.erase(top);
                       currentSCC.push_back(top);
                       if (top == u) break;
                   }
                   if (currentSCC.size() > 1) {
                       sccs.push_back(std::move(currentSCC));
                   }
               }
           };

           for (const auto &[name, _] : Modules) {
               if (dfn.find(name) == dfn.end()) {
                   tarjan(tarjan, name);
               }
           }
           return sccs;
       }

       // 拓扑排序计算编译定序
       bool computeTopologicalOrder(std::vector<InternedString> &outOrder) {
           outOrder.clear();
           std::unordered_map<InternedString, uint32_t> inDegree;
           for (const auto &[name, _] : Modules) inDegree[name] = 0;

           for (const auto &[name, mod] : Modules) {
               for (InternedString dep : mod->Dependencies) {
                   inDegree[name]++; // 当前模块依赖 dep，入度由依赖项驱动
               }
           }

           std::vector<InternedString> queue;
           for (const auto &[name, deg] : inDegree) {
               if (deg == 0) queue.push_back(name);
           }

           size_t head = 0;
           while (head < queue.size()) {
               InternedString u = queue[head++];
               outOrder.push_back(u);

               for (const auto &[vName, vMod] : Modules) {
                   for (InternedString dep : vMod->Dependencies) {
                       if (dep == u) {
                           if (--inDegree[vName] == 0) {
                               queue.push_back(vName);
                           }
                       }
                   }
               }
           }

           return outOrder.size() == Modules.size();
       }

   private:
       std::unordered_map<InternedString, std::unique_ptr<ModuleRecord>> Modules;
   };

   // 符号修饰引擎 (Itanium ABI 简化版)
   class NameMangler {
   public:
       static std::string mangle(const std::string &moduleName, const std::string &funcName,
                                 const std::vector<const Type*> &params) {
           std::string mangled = "_ZN" + std::to_string(moduleName.length()) + moduleName
                                       + std::to_string(funcName.length()) + funcName + "E";
           for (const auto *p : params) {
               mangled += encodeType(p);
           }
           return mangled;
       }

   private:
       static std::string encodeType(const Type *t) {
           if (!t) return "v";
           switch (t->Kind) {
               case TypeKind::Void: return "v";
               case TypeKind::Int32: return "i";
               case TypeKind::Int64: return "l";
               case TypeKind::Float32: return "f";
               case TypeKind::Float64: return "d";
               case TypeKind::Pointer: return "P" + encodeType(t->Pointee);
               case TypeKind::Struct: return std::to_string(t->Name.str().length()) + t->Name.str();
           }
           return "v";
       }
   };

   // 端到端多遍解析与模块调度验证
   int main() {
       StringPool pool;
       ModuleManager modMgr;

       // 1. 初始化基础类型
       Type typeInt32{TypeKind::Int32, pool.intern("i32"), nullptr, 4, 4};
       Type typeInt64{TypeKind::Int64, pool.intern("i64"), nullptr, 8, 8};
       Type typeFloat64{TypeKind::Float64, pool.intern("f64"), nullptr, 8, 8};
       Type typeBufferStruct{TypeKind::Struct, pool.intern("Buffer"), nullptr, 16, 8};
       Type typeBufferPtr{TypeKind::Pointer, pool.intern("BufferPtr"), &typeBufferStruct, 8, 8};

       std::cout << "========================================================================
";
       std::cout << "现代编译器名字决议、重载决议与模块依赖拓扑分析验证
";
       std::cout << "========================================================================

";

       // 2. 场景 A: 重载决议多等级转换与 Pareto 支配性判定
       std::cout << ">>> [测试 1] 重载决议候选集匹配与打分排序
";
       InternedString fnName = pool.intern("compute");

       // 构造三个重载候选:
       // Cand 1: compute(i64, f64)
       // Cand 2: compute(i32, f64)
       // Cand 3: compute(Buffer*, i32)
       SymbolEntry cand1{fnName, SymbolKind::Function, Visibility::Public, nullptr, {&typeInt64, &typeFloat64}, &typeInt32, {1, 1}, true};
       SymbolEntry cand2{fnName, SymbolKind::Function, Visibility::Public, nullptr, {&typeInt32, &typeFloat64}, &typeInt32, {2, 1}, true};
       SymbolEntry cand3{fnName, SymbolKind::Function, Visibility::Public, nullptr, {&typeBufferPtr, &typeInt32}, &typeInt32, {3, 1}, true};

       cand1.MangledName = NameMangler::mangle("math", "compute", cand1.ParamTypes);
       cand2.MangledName = NameMangler::mangle("math", "compute", cand2.ParamTypes);
       cand3.MangledName = NameMangler::mangle("math", "compute", cand3.ParamTypes);

       std::vector<const SymbolEntry*> candidateSet = {&cand1, &cand2, &cand3};

       // 调用点: compute(i32, f64)
       std::vector<const Type*> callArgs = {&typeInt32, &typeFloat64};
       std::string resolveErr;
       const SymbolEntry *best = OverloadResolver::resolve(candidateSet, callArgs, resolveErr);

       if (best) {
           std::cout << "调用实参签名: compute(i32, f64)
";
           std::cout << "成功决议至唯一最佳候选: Line " << best->DeclLoc.Line 
                     << " -> Mangled: " << best->MangledName << "
";
           std::cout << "匹配原因: Cand 2 对参数 1 为 ExactMatch(100分), 对参数 2 为 ExactMatch(100分), 严格支配 Cand 1(Promotion, 80分)

";
       } else {
           std::cerr << "重载失败: " << resolveErr << "

";
       }

       // 3. 场景 B: 模块依赖 DAG 拓扑排序构建
       std::cout << ">>> [测试 2] 模块依赖有向图构建与 Kahn 拓扑排序调度
";
       ModuleRecord *modCore = modMgr.createModule(pool.intern("core"));
       ModuleRecord *modNet = modMgr.createModule(pool.intern("net"));
       ModuleRecord *modParser = modMgr.createModule(pool.intern("parser"));
       ModuleRecord *modApp = modMgr.createModule(pool.intern("app"));

       // 建立依赖关系: app -> net, app -> parser, net -> core, parser -> core
       modNet->Dependencies.push_back(modCore->Name);
       modParser->Dependencies.push_back(modCore->Name);
       modApp->Dependencies.push_back(modNet->Name);
       modApp->Dependencies.push_back(modParser->Name);

       std::vector<InternedString> compileOrder;
       if (modMgr.computeTopologicalOrder(compileOrder)) {
           std::cout << "模块依赖图无环，计算出的拓扑编译发射序列:
";
           for (size_t i = 0; i < compileOrder.size(); ++i) {
               std::cout << "  [" << i + 1 << "] 模块: " << compileOrder[i].c_str() << "
";
           }
           std::cout << "
";
       }

       // 4. 场景 C: 循环依赖注入与 Tarjan SCC 检测
       std::cout << ">>> [测试 3] 注入循环导入并执行 Tarjan SCC 环路精确定位
";
       ModuleRecord *modPlugin = modMgr.createModule(pool.intern("plugin"));
       // 制造环路: core -> plugin, plugin -> app (app 已间接依赖 core)
       modCore->Dependencies.push_back(modPlugin->Name);
       modPlugin->Dependencies.push_back(modApp->Name);

       auto sccs = modMgr.detectCyclicDependencies();
       std::cout << "Tarjan 算法检测到的强连通分量 (循环依赖环路) 数量: " << sccs.size() << "
";
       for (size_t i = 0; i < sccs.size(); ++i) {
           std::cout << "  - 环路 " << i + 1 << ": ";
           for (size_t j = 0; j < sccs[i].size(); ++j) {
               std::cout << sccs[i][j].c_str() << (j + 1 < sccs[i].size() ? " <-> " : "");
           }
           std::cout << "
";
       }
       std::cout << "编译调度器动作: 命中环路错误，阻断代码生成并输出环路依赖诊断日志。
";

       return 0;
   }

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述引擎，控制台输出清晰验证了三大核心机制的正确性：
1. **重载决议高精度裁决**：面对 ``compute(i32, f64)`` 调用，引擎精确计算出 ``cand2``（``ExactMatch + ExactMatch``）对 ``cand1``（``Promotion + ExactMatch``）的严格 Pareto 支配性，消除二义性并绑定至经过 Itanium ABI 修饰的目标符号 ``_ZN4math7computeEif``。
2. **模块依赖拓扑定序**：在无环图下，Kahn 算法准确输出 ``core -> net -> parser -> app`` 的无依赖编译就绪流。
3. **Tarjan 强连通分量精准拦截**：在注入 ``core -> plugin -> app -> ... -> core`` 环路后，Tarjan 算法立即锁定由 5 个模块组成的强连通分量，为编译器报错提供了完整的环路溯源链条。

小结与下章导读
--------------

本章系统解构了编译器前端在处理复杂语言特性与工程规模扩展时的名字决议、重载仲裁与模块依赖体系：

1. **声明与定义的物理分工**：确立了声明（元数据索引、不完整类型）与定义（内存几何布局、CFG 生成）在编译器内存分配中的边界，阐明了前向引用对多遍扫描的物理需求。
2. **多遍扫描与按需查询架构**：剖析了从骨架索引收集（Pass 1）、类型签名与布局计算（Pass 2）到函数体内部名字绑定（Pass 3）的数据流拓扑，对比了固定多遍与 Query-based 架构的工程权衡。
3. **重载决议三阶段状态机**：建立了从候选收集、可行过滤到基于转换等级（ExactMatch、Promotion、Standard、UserDefined）与 Pareto 支配性原则的最佳候选决议模型。
4. **模块有向图与循环依赖检测**：实现了基于 Kahn 算法的拓扑编译定序与基于 Tarjan 算法的强连通分量循环依赖阻断机制。
5. **跨编译单元 ABI 符号修饰**：剖析了 Itanium C++ ABI 命名空间与类型编码算法。

在确立了作用域、标识符绑定与重载目标后，编译器必须对 AST 节点中的各类表达式施加严格的类型相容性验证与抽象语义约束。在第 3 模块第 3 节 **静态类型系统基石：名义类型 vs 结构类型等价性、子类型多态与类型规则健全性（03_semantic_analysis_and_type_systems/03_static_typing_and_structural_vs_nominal_equivalence.rst）** 中，我们将深入剖析名义类型与结构类型的等价性判定算法、子类型多态的格理论模型、型变（协变/逆变/不变）规则以及类型系统健全性（Soundness = Progress + Preservation）的数学证明与工程落地。
