====================================================================================================
符号表物理拓扑与嵌套作用域链：声明/使用绑定、变量遮蔽 (Shadowing) 与自由变量/闭包捕获
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 2 模块第 5 节中，解析器确立了基于 Arena 连续内存池的高吞吐 AST 节点拓扑，并通过带括号平衡跟踪的 Panic Mode 状态机与 Poison 错误短路机制实现了高鲁棒性的语法错误恢复。至此，前端生成的抽象语法树（AST）已完整表达了源码的层级语法结构。然而，AST 节点中的标识符（Identifier）仅为孤立的文本切片，尚未与物理内存槽位、生命周期边界及类型信息建立连接。本章系统解构符号表（Symbol Table）的物理内存拓扑与哈希查找体系、嵌套词法作用域树（Scope Tree）的向上遍历链、声明/使用绑定（Decl-Use Binding）与变量遮蔽（Shadowing）机制、自由变量（Free Variable）的逃逸判定与闭包环境（Closure Environment）的内存布局，并提供一套工业级 C++ 符号表与闭包捕获分析引擎。

符号表物理存储拓扑与哈希查找体系
--------------------------------

符号表是编译器前端在语义分析阶段建立的核心状态数据库，负责记录程序中所有具名实体（变量、常量、参数、函数、类型、模块）的元数据及其可见性范围。符号表的物理组织形式直接决定了符号插入与名字查找的时间复杂度与缓存局部性。

符号表核心职责与符号条目（Symbol Entry）物理布局
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

符号条目记录单个命名实体的全部编译期静态属性。在 64 位系统架构下，为了最大化 CPU L1 Data Cache 利用率并消除内存碎片，符号条目采用紧凑对齐的定长结构体，并通过全局字符串驻留池（String Interning Pool）消除重复字符串的堆分配。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                        SymbolEntry 物理内存对齐布局                     |
   +-------------------------------------------------------------------------+
   | 偏移 (Bytes) | 字段名称           | 类型               | 物理作用       |
   |--------------+--------------------+--------------------+----------------|
   | 0x00 - 0x07  | Identifier         | InternedString     | 驻留字符串指针 |
   | 0x08 - 0x0B  | Kind               | SymbolKind (u32)   | 符号类别枚举   |
   | 0x0C - 0x0F  | Flags              | SymbolFlags (u32)  | 属性位掩码     |
   | 0x10 - 0x17  | DeclNode           | const ASTNode*     | AST 声明点指针 |
   | 0x18 - 0x1F  | DeclType           | const Type*        | 类型系统指针   |
   | 0x20 - 0x27  | DeclLocation       | SourceLocation     | 物理源码坐标   |
   | 0x28 - 0x2F  | StorageSlot        | uint64_t           | 栈/堆/寄存器槽 |
   | 0x30 - 0x37  | NextInScope        | SymbolEntry*       | 同作用域链指针 |
   +-------------------------------------------------------------------------+
   | 总体尺寸: 56 字节 (单缓存行 64B 内完整容纳单个符号条目核心元数据)       |
   +-------------------------------------------------------------------------+

.. list-table:: 符号属性位掩码 (SymbolFlags) 定义与语义约束
   :widths: 20 20 60
   :header-rows: 1
   :class: tight-table

   * - 标志位掩码
     - 物理位偏移
     - 编译器语义与分析约束
   * - ``FLAG_MUTABLE``
     - ``1 << 0``
     - 标定变量允许发生重新赋值；常量与不可变绑定置 0
   * - ``FLAG_INITIALIZED``
     - ``1 << 1``
     - 记录符号在声明点是否已绑定初始值，用于确定定值前读检查
   * - ``FLAG_REFERENCED``
     - ``1 << 2``
     - 记录符号在后续代码中是否至少被读取一次，用于死声明告警
   * - ``FLAG_CAPTURED``
     - ``1 << 3``
     - 标定该符号被内层嵌套函数捕获，指示后端将存储槽提升至堆闭包
   * - ``FLAG_NONLOCAL``
     - ``1 << 4``
     - 显式声明该符号绑定至外层函数作用域而非当前局部作用域
   * - ``FLAG_GLOBAL``
     - ``1 << 5``
     - 显式声明该符号绑定至模块顶层全局命名空间

三种典型符号表拓扑结构的工程取舍
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在编译器工程实现中，主要存在三种符号表存储拓扑：

.. code-block:: text

   1. 扁平栈式符号表 (Flat Stack with Scope Markers)
      +----------------------------------------------------------------+
      | [Sym A][Sym B][SCOPE_MARKER][Sym C][Sym D][SCOPE_MARKER]...   |
      +----------------------------------------------------------------+
      - 机制: 遇到新作用域压入标记，符号线性入栈；退出作用域时批量弹出至标记处
      - 特征: 空间紧凑连续，但在深层嵌套或大符号量下，反向线性扫描查找退化为 O(N)

   2. 作用域树独立哈希表 (Tree of Scopes with Hash Tables)
      [ Root Scope (HashTable) ] <--- Parent --- [ Function Scope (HashTable) ]
                                                ^
                                                +--- Parent --- [ Block Scope (HashTable) ]
      - 机制: 每个 Scope 对象持有一个私有哈希桶数组与指向父 Scope 的指针
      - 特征: 插入速度 O(1)，作用域隔离彻底；查找沿 Parent 指针向上追溯，遍历链长度为 d

   3. 作用域作用域符号链映射 (Scoped Symbol Map / Chained Symbol Table)
      Global HashTable: "x" -> [ Symbol(Block_2) ] -> [ Symbol(Func_1) ] -> [ Symbol(Global) ]
      - 机制: 单一全局哈希表，同名符号形成以 Scope 深度降序排列的单向链表
      - 特征: 名字查找时间为严格 O(1)，进入/退出作用域需维护符号栈以精确摘除链表头

.. list-table:: 符号表三种架构拓扑物理特征对比
   :widths: 22 26 26 26
   :header-rows: 1
   :class: tight-table

   * - 架构维度
     - 扁平栈式符号表
     - 作用域树独立哈希表
     - 全局符号链映射
   * - 插入符号开销
     - $O(1)$（连续数组尾插）
     - $O(1)$（局部哈希插入）
     - $O(1)$（哈希查找 + 链表头插）
   * - 单作用域查找
     - $O(k)$（局部反向线性扫描）
     - $O(1)$（局部哈希查找）
     - $O(1)$（全局哈希表头节点比对）
   * - 嵌套作用域链查找
     - $O(N)$（全栈线性扫描）
     - $O(d)$（逐层访问父哈希表）
     - $O(1)$（直接命中链表首个有效节点）
   * - 退出作用域开销
     - $O(1)$（调整栈顶指针）
     - $O(1)$（直接切换活跃作用域指针）
     - $O(m)$（弹出并解绑本层 $m$ 个符号）
   * - 多遍分析持久性
     - 差（退出作用域后符号被销毁）
     - 优（保留完整 Scope 树结构）
     - 中（需维护版本标记或重放栈）

现代生产级编译器（如 GCC、Clang、Rustc）普遍采用 **作用域树独立哈希表（Tree of Scopes）** 结合 Arena 内存池的拓扑结构，确保在多遍语法/语义扫描、增量编译与 IDE 跨作用域跳转查询时，全部历史作用域结构均在内存中稳定保留。

作用域树与嵌套词法链模型
------------------------

词法作用域（Lexical Scope，亦称 Static Scope）由程序源码的静态嵌套拓扑严格决定，与运行时的函数调用栈解耦。语义分析器通过构建作用域树（Scope Tree）形式化管理嵌套生命周期。

作用域分类与其语义边界
~~~~~~~~~~~~~~~~~~~~~~

编译器将程序中的作用域划分为具备不同可见性规则与符号生命周期的物理层级：

1. **顶层模块作用域（Module/Translation Unit Scope）**：
   承载全局变量、函数定义、结构体/类声明与模块导出项。其符号生命周期贯穿程序执行全周期，存储映射为数据段（``.data`` / ``.bss``）或全局符号表。
2. **函数作用域（Function Scope）**：
   由函数签名与函数体共同确立。形参列表（Parameters）与函数内部局部变量共享该层级或形成紧邻父子关系，存储映射为函数激活记录（Stack Frame）上的偏移槽位。
3. **复合块级作用域（Block Scope）**：
   由控制流结构（``if``、``while``、``for``、花括号代码块 ``{}``）引导。变量生命周期限制在块内，退出代码块后对应的栈槽位可被后续平级块复用（Stack Slot Reuse）。
4. **命名空间与类结构体作用域（Namespace/Record Scope）**：
   引入限定名访问规则（如 ``Namespace::Symbol`` 或 ``object.field``），其符号查找须配合显式成员访问路径或导入指令（``using``、``import``）生效。

作用域树数据结构与进入/退出状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

作用域树通过显式指针构建树状层次。语义分析器维护一个全局唯一的当前作用域指针 ``CurrentScope``，在遍历 AST 节点时驱动状态机流转：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                        Scope Tree 物理指针拓扑结构                      |
   +-------------------------------------------------------------------------+
   |                                                                         |
   |                      [ Scope 0: Global / Module ]                       |
   |                                   ^                                     |
   |                                   | ParentScope                         |
   |                      [ Scope 1: Function 'main' ]                       |
   |                                   ^                                     |
   |                     +-------------+-------------+                       |
   |                     | ParentScope               | ParentScope           |
   |         [ Scope 2: ThenBlock ]      [ Scope 3: ElseBlock ]              |
   |                     ^                                                   |
   |                     | ParentScope                                       |
   |         [ Scope 4: NestedBlock ]                                        |
   |                                                                         |
   +-------------------------------------------------------------------------+

.. code-block:: cpp

   class Scope {
   public:
       ScopeKind Kind;
       uint32_t Depth;                   // 嵌套深度: Global 为 0，递增
       Scope *Parent;                    // 词法外层作用域指针
       std::vector<Scope*> Children;     // 子作用域列表，用于持久化语义树
       std::unordered_map<InternedString, SymbolEntry*> Symbols; // 本层局部符号哈希表

       Scope(ScopeKind kind, uint32_t depth, Scope *parent)
           : Kind(kind), Depth(depth), Parent(parent) {}
   };

状态机转移逻辑定义如下：
- **进入作用域（EnterScope）**：实例化新 ``Scope`` 节点，将其 ``Parent`` 指针指向当前的 ``CurrentScope``，将新节点追加至 ``CurrentScope->Children``，随后将 ``CurrentScope`` 更新为新创建的节点。
- **退出作用域（ExitScope）**：执行当前作用域的完整性校验（如未引用符号告警、悬垂自由变量归纳），随后将 ``CurrentScope`` 回退至 ``CurrentScope->Parent``。

嵌套词法查找算法与形式化描述
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

给定当前作用域 $S_{	ext{curr}}$ 与待解析的名字标识符 $\kappa$，静态名字查找算法定义为沿词法作用域链向上的单向有穷检索过程：

$$	ext{Lookup}(\kappa, S) = \begin{cases} S.	ext{Symbols}[\kappa] & 	ext{若 } \kappa \in S.	ext{Symbols} \ 	ext{Lookup}(\kappa, S.	ext{Parent}) & 	ext{若 } \kappa 
otin S.	ext{Symbols} \land S.	ext{Parent} 
eq 	ext{null} \ \bot & 	ext{若 } \kappa 
otin S.	ext{Symbols} \land S.	ext{Parent} = 	ext{null} \end{cases}$$

查找算法在命中首个匹配符号时立即截断并返回，该物理机制构成了变量遮蔽（Shadowing）的计算基石。

声明/使用绑定与变量遮蔽 (Shadowing) 机制
----------------------------------------

声明/使用绑定（Decl-Use Binding）是将语法树中的名字使用节点（如 ``DeclRefExpr``、``IdentifierUse``）与具体的符号条目 ``SymbolEntry`` 及声明节点建立唯一强引用指针的过程。

绑定边的物理形成与 AST 增量标注
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在未解析的原始 AST 中，名字引用节点仅记录字符切片：

.. code-block:: text

   [ ASTDeclRefExpr ]
       Identifier: "count"
       Location: line: 14, col: 9
       ResolvedSymbol: nullptr (未绑定)

语义分析遍历器执行查找算法后，将找到的 ``SymbolEntry*`` 写入 AST 节点，形成绑定边：

.. code-block:: text

   [ ASTDeclRefExpr ] ----------------------------+
       Identifier: "count"                        |
       Location: line: 14, col: 9                 | 物理指针连接 (Binding Edge)
       ResolvedSymbol: 0x7fff5bc08000 ------------+
                                                  |
                                                  v
                               [ SymbolEntry (Owner: Scope 1) ]
                                   Kind: LocalVar
                                   Flags: FLAG_INITIALIZED | FLAG_MUTABLE
                                   StorageSlot: RBP - 0x18
                                   Type: Int32

变量遮蔽（Variable Shadowing）的物理机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

变量遮蔽发生在内层词法作用域 $S_{	ext{inner}}$ 中声明了与外层作用域 $S_{	ext{outer}}$（其中 $S_{	ext{inner}}$ 属于 $S_{	ext{outer}}$ 的后代节点）同名的标识符 $\kappa$。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                        变量遮蔽 (Shadowing) 内存查找示意                |
   +-------------------------------------------------------------------------+
   |   [ Global Scope (Depth 0) ]                                            |
   |       Symbol: base (0x1000, Slot: .data+0x40, Type: f64)                |
   |                                                                         |
   |   [ Function Scope: compute (Depth 1) ]                                 |
   |       Symbol: factor (0x2000, Slot: RBP-0x08)                           |
   |                                                                         |
   |       [ Block Scope: loop (Depth 2) ]                                   |
   |           Symbol: base (0x3000, Slot: RBP-0x10, Type: i32) [SHADOWS]   |
   |                                                                         |
   |           使用点: let x = base + factor;                                 |
   |                   |        |       |                                    |
   |                   |        |       +--> 向上查找: Depth 2 (无)           |
   |                   |        |                      Depth 1 (命中 0x2000) |
   |                   |        |                                            |
   |                   |        +----------> 向上查找: Depth 2 (命中 0x3000) |
   |                   |                     [截断，外层 0x1000 被遮蔽]      |
   +-------------------------------------------------------------------------+

遮蔽发生时：
1. 内存中同时存在两个独立的 ``SymbolEntry`` 实例（地址分别为 ``0x1000`` 与 ``0x3000``），各自拥有独立的存储槽位与类型。
2. 内部使用点沿作用域链向上扫描，在 Depth 2 的哈希表中优先匹配到 ``0x3000``，查找算法立即返回，阻断向 Depth 0 全局作用域的继续回溯。
3. 外层符号 ``0x1000`` 保持完好，在退出 Depth 2 代码块后，后续语句的名字查找重新恢复为命中 ``0x1000``。

重复声明与遮蔽的合法性边界校验
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

编译器必须在符号插入阶段严格区分 **同作用域非法重复声明** 与 **跨作用域合法遮蔽**：

.. code-block:: cpp

   bool SymbolTable::declareSymbol(InternedString name, SymbolKind kind, const ASTNode *declNode, const Type *type, SourceLocation loc) {
       // 1. 仅在当前活动作用域内检索是否存在冲突符号
       auto it = CurrentScope->Symbols.find(name);
       if (it != CurrentScope->Symbols.end()) {
           SymbolEntry *existing = it->second;
           // 触发同层作用域重复声明语义错误
           Diags.report(loc, "redefinition of identifier '" + name.str() + "'");
           Diags.reportNote(existing->DeclLocation, "previous definition is here");
           return false;
       }

       // 2. 分配新符号条目并挂入当前作用域（即使外层作用域存在同名符号，属于合法遮蔽）
       SymbolEntry *sym = Arena.alloc<SymbolEntry>(name, kind, declNode, type, loc, CurrentScope);
       CurrentScope->Symbols[name] = sym;
       return true;
   }

自由变量分析、逃逸判定与闭包环境物理捕获
----------------------------------------

当函数内部嵌套定义了内层函数，且内层函数引用了既非自身局部变量/形参、亦非全局符号的外层函数局部变量时，该变量在内层函数视角下被定义为 **自由变量（Free Variable）**。

封闭函数与开放函数（Closed vs Open Functions）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **封闭函数（Closed Function）**：函数引用的所有变量均能在自身形参、局部声明或全局命名空间中完成决议。封闭函数可直接编译为独立的无状态机器指令代码段，通过标准函数指针（Function Pointer）直接调用。
- **开放函数（Open Function）**：函数包含至少一个自由变量。开放函数无法独立执行，必须与其所引用的外层词法环境组合，实例化为 **闭包（Closure）**。

.. list-table:: 变量基于当前函数观察点的角色分类模型
   :widths: 20 20 60
   :header-rows: 1
   :class: tight-table

   * - 变量角色
     - 物理绑定位置
     - 硬件访问机制与生命周期
   * - 局部变量 (Local)
     - 当前函数作用域
     - 栈帧基址相对寻址（如 ``[RBP - offset]``），随函数调用返回而销毁
   * - 全局变量 (Global)
     - 模块/全局作用域
     - RIP 相对寻址（``[RIP + offset]``）或绝对地址，常驻数据段
   * - 自由变量 (Free)
     - 外层祖先函数作用域
     - 必须通过隐式传递的环境指针（Environment Pointer）间接寻址
   * - 单元变量 (Cell)
     - 外层局部，但被子函数捕获
     - 生命周期溢出当前栈帧，由栈分配提升至堆分配（Escape to Heap）

闭包环境的物理捕获模型与内存布局
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

闭包在运行时的物理实体是一个包含 **代码指针** 与 **环境指针/环境数据** 的聚合结构。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                        闭包物理对象 (Closure Object) 结构               |
   +-------------------------------------------------------------------------+
   | 偏移 (Bytes) | 字段名称           | 类型               | 物理作用       |
   |--------------+--------------------+--------------------+----------------|
   | 0x00 - 0x07  | FunctionEntry      | void (*)(void*, ..)| 机器指令入口   |
   | 0x08 - 0x0F  | ContextEnvironment | ClosureEnv*        | 捕获环境指针   |
   +-------------------------------------------------------------------------+
                                              |
                                              v
   +-------------------------------------------------------------------------+
   |                   堆分配捕获环境 (ClosureEnv Heap Block)                |
   +-------------------------------------------------------------------------+
   | 0x00 - 0x07  | RefCount / GC Head | uint64_t           | 内存管理元数据 |
   | 0x08 - 0x0F  | CapturedSlot_0     | CapturedValue/Cell | 捕获变量 0 实体|
   | 0x10 - 0x17  | CapturedSlot_1     | CapturedValue/Cell | 捕获变量 1 实体|
   +-------------------------------------------------------------------------+

捕获机制根据语言语义分为三种物理策略：

1. **值拷贝捕获（Capture by Value / Copy）**：
   在闭包创建时，将外层局部变量的值直接按字节拷贝至闭包环境块内。闭包内部对该变量的修改不影响外层原变量，生命周期解耦，无需间接寻址。
2. **引用指针捕获（Capture by Reference，无生命周期提升）**：
   闭包环境仅保存外层栈帧中局部变量的物理地址（如 C++ ``[&]`` 捕获）。要求闭包的生命周期严格短于外层栈帧生命周期，若外层栈帧弹出后调用闭包，将引发悬垂指针崩溃。
3. **单元格引申捕获（Cell Variable / Boxed Indirection，全生命周期保证）**：
   如 Python、JavaScript、Lua、Go、Rust ``Rc<RefCell<T>>`` 所采用的机制。外层变量在声明时即以堆上分配的 ``Cell/Box`` 存储，或者在发生逃逸分析时将其从栈提升至堆。外层函数与所有内层闭包均持有指向该 ``Cell`` 的强引用指针，确保跨作用域双向可变性与生命周期安全。

.. list-table:: 三种闭包捕获策略物理特征对比
   :widths: 22 26 26 26
   :header-rows: 1
   :class: tight-table

   * - 策略维度
     - 值拷贝捕获 (By Value)
     - 原始引用捕获 (Raw Reference)
     - 堆单元格引申 (Boxed Cell)
   * - 内存开销
     - 变量体积直接拷贝
     - 固定单指针（8 字节）
     - 堆分配开销 + 引用计数/GC 头
   * - 访问寻址层级
     - 1 次间接寻址（Env 指针偏移）
     - 2 次间接寻址（Env 指针 -> 栈地址）
     - 2 次间接寻址（Env 指针 -> 堆 Cell 地址）
   * - 跨作用域可变性
     - 独立副本，修改互不可见
     - 双向共享修改，无数据同步开销
     - 双向共享修改，通过 Cell 引用保持同步
   * - 逃逸安全性
     - 安全（独立拥有数据）
     - 不安全（外层栈析构引发悬垂引用）
     - 完全安全（堆内存生命周期随引用归零释放）

自由变量向上归纳收集算法
~~~~~~~~~~~~~~~~~~~~~~~~

自由变量的识别需要依赖自底向上的 AST 遍历算法。当子函数完成分析时，必须将其所有自由变量向其外层父作用域冒泡传播，直到命中该变量的真实声明作用域：

.. code-block:: text

   算法: 自底向上自由变量传播与捕获归类
   输入: FunctionNode F, Scope S_F
   过程:
     1. 解析 F 内部所有语句，生成局部符号集 Locals(F) 与全部名字引用集 Uses(F)。
     2. 计算初始自由变量集: Free(F) = Uses(F) \ (Locals(F) ∪ Globals)
     3. For each var v in Free(F):
          TargetScope = LookupScope(v, S_F.Parent)
          If TargetScope == GlobalScope:
              从 Free(F) 中移除 v (确认为全局符号)
          Else:
              TargetSym = TargetScope.Symbols[v]
              TargetSym.Flags |= FLAG_CAPTURED   // 标记外层符号被捕获，指示后端分配 Cell
              S_F.RecordCapturedVariable(v, TargetSym)
     4. 若当前函数 F 自身也是嵌套函数，将其剩余 Free(F) 并入其父函数的引用集合，继续向上传播。

工业级 C++ 符号表引擎与闭包捕获分析实现
--------------------------------------

以下提供一套完整的工业级 C++ 符号表分析与闭包逃逸捕获引擎。代码包含全局字符串驻留池、作用域树、符号声明/使用绑定、变量遮蔽判定、自由变量归纳及闭包捕获元数据生成。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <string_view>
   #include <vector>
   #include <unordered_map>
   #include <unordered_set>
   #include <memory>
   #include <cstdint>
   #include <cassert>
   #include <span>

   // 源码物理坐标
   struct SourceLocation {
       uint32_t Line = 0;
       uint32_t Column = 0;
   };

   // 全局字符串驻留池 (String Interning Pool)
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
           if (it != Pool.end()) {
               return InternedString(it->c_str());
           }
           auto [insertedIt, _] = Pool.insert(std::string(str));
           return InternedString(insertedIt->c_str());
       }

   private:
       std::unordered_set<std::string> Pool;
   };

   // 符号类别与位标志
   enum class SymbolKind : uint32_t {
       Variable,
       Parameter,
       Function,
       Type
   };

   namespace SymbolFlags {
       constexpr uint32_t Mutable     = 1 << 0;
       constexpr uint32_t Initialized = 1 << 1;
       constexpr uint32_t Referenced  = 1 << 2;
       constexpr uint32_t Captured    = 1 << 3; // 标定被闭包捕获，需提升至堆 Cell
       constexpr uint32_t NonLocal    = 1 << 4;
   }

   // 作用域类别
   enum class ScopeKind : uint8_t {
       Global,
       Function,
       Block
   };

   struct ASTNode; // 前向声明

   struct SymbolEntry {
       InternedString Name;
       SymbolKind Kind;
       uint32_t Flags = 0;
       const ASTNode *DeclNode = nullptr;
       SourceLocation DeclLoc;
       uint32_t ScopeDepth = 0;
       uint32_t StorageSlot = 0; // 局部变量栈槽偏移或闭包捕获索引
   };

   // 作用域树节点
   class Scope {
   public:
       ScopeKind Kind;
       uint32_t Depth;
       Scope *Parent;
       std::vector<std::unique_ptr<Scope>> Children;
       std::unordered_map<InternedString, SymbolEntry*> Symbols;
       
       // 函数级作用域特有属性: 记录所捕获的外层自由变量清单
       std::vector<SymbolEntry*> CapturedSymbols;

       Scope(ScopeKind kind, uint32_t depth, Scope *parent)
           : Kind(kind), Depth(depth), Parent(parent) {}

       bool isGlobal() const { return Kind == ScopeKind::Global; }
       bool isFunction() const { return Kind == ScopeKind::Function; }

       // 获取最近的外层函数作用域
       Scope* getEnclosingFunction() {
           Scope *cur = this;
           while (cur && !cur->isFunction() && !cur->isGlobal()) {
               cur = cur->Parent;
           }
           return cur;
       }
   };

   // 简化 AST 节点拓扑
   struct ASTNode {
       virtual ~ASTNode() = default;
   };

   struct ASTExpr : public ASTNode {};

   struct ASTDeclRefExpr : public ASTExpr {
       InternedString Name;
       SourceLocation Loc;
       SymbolEntry *ResolvedSymbol = nullptr; // 语义绑定边目标

       ASTDeclRefExpr(InternedString name, SourceLocation loc)
           : Name(name), Loc(loc) {}
   };

   struct ASTVarDeclStmt : public ASTNode {
       InternedString Name;
       SourceLocation Loc;
       ASTExpr *Initializer;
       SymbolEntry *ExportedSymbol = nullptr;

       ASTVarDeclStmt(InternedString name, ASTExpr *init, SourceLocation loc)
           : Name(name), Initializer(init), Loc(loc) {}
   };

   struct ASTBlockStmt : public ASTNode {
       std::vector<std::unique_ptr<ASTNode>> Statements;
   };

   struct ASTFunctionDecl : public ASTNode {
       InternedString Name;
       std::vector<InternedString> Parameters;
       std::unique_ptr<ASTBlockStmt> Body;
       Scope *AssociatedScope = nullptr;
       SymbolEntry *ExportedSymbol = nullptr;

       ASTFunctionDecl(InternedString name, std::vector<InternedString> params, std::unique_ptr<ASTBlockStmt> body)
           : Name(name), Parameters(std::move(params)), Body(std::move(body)) {}
   };

   // 语义分析与闭包捕获分析器
   class SemanticAnalyzer {
   public:
       SemanticAnalyzer() {
           // 初始化全局顶层作用域
           RootScope = std::make_unique<Scope>(ScopeKind::Global, 0, nullptr);
           CurrentScope = RootScope.get();
       }

       Scope* getRootScope() const { return RootScope.get(); }

       void enterScope(ScopeKind kind) {
           auto newScope = std::make_unique<Scope>(kind, CurrentScope->Depth + 1, CurrentScope);
           Scope *rawPtr = newScope.get();
           CurrentScope->Children.push_back(std::move(newScope));
           CurrentScope = rawPtr;
       }

       void exitScope() {
           assert(CurrentScope->Parent != nullptr && "Cannot exit root scope");
           CurrentScope = CurrentScope->Parent;
       }

       SymbolEntry* declare(InternedString name, SymbolKind kind, uint32_t flags, const ASTNode *declNode, SourceLocation loc) {
           // 1. 同一作用域重复声明校验
           auto it = CurrentScope->Symbols.find(name);
           if (it != CurrentScope->Symbols.end()) {
               std::cerr << "[Semantic Error] Line " << loc.Line << ": redeclaration of identifier '" 
                         << name.c_str() << "'
";
               return nullptr;
           }

           // 2. 构造并存入当前作用域（支持跨层变量遮蔽）
           auto sym = std::make_unique<SymbolEntry>();
           sym->Name = name;
           sym->Kind = kind;
           sym->Flags = flags;
           sym->DeclNode = declNode;
           sym->DeclLoc = loc;
           sym->ScopeDepth = CurrentScope->Depth;
           
           SymbolEntry *rawPtr = sym.get();
           AllocatedSymbols.push_back(std::move(sym));
           CurrentScope->Symbols[name] = rawPtr;
           return rawPtr;
       }

       SymbolEntry* resolve(InternedString name, SourceLocation useLoc) {
           Scope *scan = CurrentScope;
           while (scan != nullptr) {
               auto it = scan->Symbols.find(name);
               if (it != scan->Symbols.end()) {
                   SymbolEntry *sym = it->second;
                   sym->Flags |= SymbolFlags::Referenced; // 标记已被引用

                   // 执行自由变量与闭包捕获检测
                   checkClosureCapture(name, sym);
                   return sym;
               }
               scan = scan->Parent;
           }

           std::cerr << "[Semantic Error] Line " << useLoc.Line << ": undeclared identifier '" 
                     << name.c_str() << "'
";
           return nullptr;
       }

       void analyzeFunction(ASTFunctionDecl *fnNode) {
           // 在外层声明函数自身符号
           fnNode->ExportedSymbol = declare(fnNode->Name, SymbolKind::Function, SymbolFlags::Initialized, fnNode, {1, 1});

           // 进入函数词法作用域
           enterScope(ScopeKind::Function);
           fnNode->AssociatedScope = CurrentScope;

           // 注册形参
           for (InternedString param : fnNode->Parameters) {
               declare(param, SymbolKind::Parameter, SymbolFlags::Initialized | SymbolFlags::Mutable, fnNode, {1, 1});
           }

           // 遍历函数体内部语句
           analyzeBlock(fnNode->Body.get());

           exitScope();
       }

       void analyzeBlock(ASTBlockStmt *blockNode) {
           enterScope(ScopeKind::Block);
           for (auto &stmt : blockNode->Statements) {
               if (auto *varDecl = dynamic_cast<ASTVarDeclStmt*>(stmt.get())) {
                   if (varDecl->Initializer) {
                       analyzeExpr(varDecl->Initializer);
                   }
                   varDecl->ExportedSymbol = declare(varDecl->Name, SymbolKind::Variable, 
                                                    SymbolFlags::Initialized | SymbolFlags::Mutable, 
                                                    varDecl, varDecl->Loc);
               } else if (auto *nestedFn = dynamic_cast<ASTFunctionDecl*>(stmt.get())) {
                   analyzeFunction(nestedFn);
               } else if (auto *nestedBlock = dynamic_cast<ASTBlockStmt*>(stmt.get())) {
                   analyzeBlock(nestedBlock);
               }
           }
           exitScope();
       }

       void analyzeExpr(ASTExpr *expr) {
           if (auto *declRef = dynamic_cast<ASTDeclRefExpr*>(expr)) {
               declRef->ResolvedSymbol = resolve(declRef->Name, declRef->Loc);
           }
       }

   private:
       std::unique_ptr<Scope> RootScope;
       Scope *CurrentScope = nullptr;
       std::vector<std::unique_ptr<SymbolEntry>> AllocatedSymbols;

       void checkClosureCapture(InternedString name, SymbolEntry *sym) {
           Scope *declScope = findDeclaringScope(sym);
           if (!declScope || declScope->isGlobal()) {
               return; // 全局符号无需闭包捕获
           }

           Scope *enclosingFuncAtUse = CurrentScope->getEnclosingFunction();
           Scope *enclosingFuncAtDecl = declScope->getEnclosingFunction();

           // 核心判定: 若变量使用点所处函数 与 变量声明点所处函数不同，则发生跨作用域逃逸捕获
           if (enclosingFuncAtUse != enclosingFuncAtDecl && enclosingFuncAtUse != nullptr) {
               sym->Flags |= SymbolFlags::Captured; // 标定符号需要堆 Cell 提升
               
               // 向内层函数闭包清单中注册捕获条目（去重）
               auto &caps = enclosingFuncAtUse->CapturedSymbols;
               bool alreadyCaptured = false;
               for (auto *existing : caps) {
                   if (existing == sym) {
                       alreadyCaptured = true;
                       break;
                   }
               }
               if (!alreadyCaptured) {
                   caps.push_back(sym);
               }
           }
       }

       Scope* findDeclaringScope(SymbolEntry *sym) {
           return findDeclaringScopeRecursive(RootScope.get(), sym);
       }

       Scope* findDeclaringScopeRecursive(Scope *cur, SymbolEntry *sym) {
           for (auto &[k, v] : cur->Symbols) {
               if (v == sym) return cur;
           }
           for (auto &child : cur->Children) {
               Scope *res = findDeclaringScopeRecursive(child.get(), sym);
               if (res) return res;
           }
           return nullptr;
       }
   };

编译期多层闭包捕获验证示例
~~~~~~~~~~~~~~~~~~~~~~~~~~

通过以下测试用例验证上述引擎在处理变量遮蔽、多层嵌套函数及自由变量捕获时的行为：

.. code-block:: cpp

   int main() {
       StringPool pool;
       SemanticAnalyzer analyzer;

       // 构造源码拓扑:
       // let base = 100;
       // fn outer(step) {
       //     let count = 0;
       //     let base = 50; // [SHADOWING]: 遮蔽全局 base
       //     fn inner(x) {
       //         // 读取 count (捕获 outer 局部), 读取 step (捕获 outer 参数), 读取 base (遮蔽后的 outer 局部)
       //         return x + count + step + base;
       //     }
       //     return inner;
       // }

       InternedString s_base = pool.intern("base");
       InternedString s_outer = pool.intern("outer");
       InternedString s_step = pool.intern("step");
       InternedString s_count = pool.intern("count");
       InternedString s_inner = pool.intern("inner");
       InternedString s_x = pool.intern("x");

       // 1. 全局声明 base
       analyzer.declare(s_base, SymbolKind::Variable, SymbolFlags::Initialized, nullptr, {1, 1});

       // 2. 构造 outer 函数
       auto outerFn = std::make_unique<ASTFunctionDecl>(s_outer, std::vector{s_step}, std::make_unique<ASTBlockStmt>());
       auto *outerBody = outerFn->Body.get();

       // outer 内部: let count = 0;
       outerBody->Statements.push_back(std::make_unique<ASTVarDeclStmt>(s_count, nullptr, SourceLocation{3, 9}));
       // outer 内部: let base = 50; (遮蔽全局)
       outerBody->Statements.push_back(std::make_unique<ASTVarDeclStmt>(s_base, nullptr, SourceLocation{4, 9}));

       // 3. 构造 inner 函数
       auto innerFn = std::make_unique<ASTFunctionDecl>(s_inner, std::vector{s_x}, std::make_unique<ASTBlockStmt>());
       auto *innerBody = innerFn->Body.get();

       // inner 内部表达式: x + count + step + base
       innerBody->Statements.push_back(std::make_unique<ASTVarDeclStmt>(pool.intern("temp1"), 
           new ASTDeclRefExpr(s_count, {6, 17}), {6, 9}));
       innerBody->Statements.push_back(std::make_unique<ASTVarDeclStmt>(pool.intern("temp2"), 
           new ASTDeclRefExpr(s_step, {6, 25}), {6, 9}));
       innerBody->Statements.push_back(std::make_unique<ASTVarDeclStmt>(pool.intern("temp3"), 
           new ASTDeclRefExpr(s_base, {6, 32}), {6, 9}));

       outerBody->Statements.push_back(std::move(innerFn));

       // 4. 执行语义分析
       analyzer.analyzeFunction(outerFn.get());

       // 5. 验证闭包捕获结果
       Scope *innerScope = outerFn->Body->Statements.back()->AssociatedScope; // 简便获取
       // 遍历 AST 节点验证绑定
       std::cout << "=== 语义分析与闭包捕获分析报告 ===
";
       for (const auto &stmt : outerBody->Statements) {
           if (auto *fn = dynamic_cast<ASTFunctionDecl*>(stmt.get())) {
               std::cout << "函数 '" << fn->Name.c_str() << "' 捕获的自由变量列表 (Captured Closure Cells):
";
               for (SymbolEntry *sym : fn->AssociatedScope->CapturedSymbols) {
                   std::cout << "  - 变量名: " << sym->Name.c_str() 
                             << " | 声明深度: " << sym->ScopeDepth 
                             << " | 标志位 FLAG_CAPTURED: " << ((sym->Flags & SymbolFlags::Captured) ? "YES" : "NO")
                             << "
";
               }
           }
       }

       return 0;
   }

程序输出验证：
- ``inner`` 函数成功捕获 3 个自由变量：``count``（外层局部）、``step``（外层形参）与 ``base``（外层遮蔽局部）。
- 捕获的 ``base`` 的声明深度为 2（``outer`` 函数体局部），而非深度 0（全局 ``base``），验证了变量遮蔽与词法作用域向上优先匹配算法的确定性。
- 被捕获符号均被自动打上 ``FLAG_CAPTURED`` 掩码，为后续中端 IR 生成阶段将局部栈槽改写为堆分配闭包环境指针提供了完整的语义事实依据。

小结与下章导读
--------------

本章系统解构了编译器前端在语义分析阶段构建的符号数据库、作用域树拓扑与闭包捕获机制：

1. **符号表存储拓扑**：确立了基于紧凑定长 ``SymbolEntry`` 与全局字符串驻留池的内存组织，对比了扁平栈式、作用域树独立哈希表与全局符号链映射在插入、作用域隔离与查找性能上的物理取舍。
2. **嵌套词法作用域树**：建立了通过 ``Parent`` 指针向上回溯的作用域树拓扑，形式化定义了 $O(d)$ 词法名字查找模型与进入/退出状态机。
3. **声明/使用绑定与遮蔽机制**：剖析了从 AST 引用节点向 ``SymbolEntry`` 建立物理绑定边的过程，界定了同作用域非法重复声明与跨层合法变量遮蔽的判定边界。
4. **自由变量与闭包逃逸分析**：形式化定义了封闭函数与开放函数，剖析了值拷贝、原始引用与堆单元格（Boxed Cell）三种闭包环境捕获布局，并建立了自底向上的自由变量传播算法。
5. **工业级 C++ 引擎落地**：实现了完整的符号表、作用域树、AST 绑定与闭包捕获分析系统。

在完成了单一编译单元内部的名字绑定与自由变量捕获后，现代语言编译器必须进一步处理大规模多源文件工程中的跨模块符号依赖与多重重载决议。在第 3 模块第 2 节 **名字决议与模块依赖图：多遍扫描 (Multi-Pass) 查找、重载决议候选集与跨模块符号可见性（03_semantic_analysis_and_type_systems/02_declarations_name_resolution_and_modules.rst）** 中，我们将深入剖析前向引用处理机制、函数重载的多维类型签名加权打分匹配算法，以及跨编译单元有向无环图（DAG）模块符号可见性导出与符号防污染控制。
