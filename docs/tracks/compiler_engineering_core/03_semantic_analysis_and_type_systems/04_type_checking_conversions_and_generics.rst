====================================================================================================
表达式类型检查与泛型实例化：隐式转换截断、单态化 (Monomorphization) 与类型擦除
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 3 模块第 3 节中，编译器确立了名义类型与结构类型的等价性判定法则、基于偏序格（Type Lattice）的子类型多态机制、函数参数逆变与返回值协变定理，以及 Wright-Felleisen 框架下类型健全性（Progress + Preservation）的理论基石。然而，建立类型系统的公理体系仅完成了静态语义规则的定义。当抽象语法树（AST）进入实际遍历阶段时，编译器必须为树中的每一个表达式节点判定具体的类型事实，在类型失配时插入物理转换指令，并在遇到参数化多态（Parametric Polymorphism）时决定是将泛型代码特化为独立的目标机器码还是降级为共享的通用表示。本章深入剖析表达式双向类型检查（Bidirectional Type Checking）的工作机制、隐式数值转换与位宽截断在硬件寄存器层面的物理行为、基于 AST 克隆与符号重整（Name Mangling）的泛型单态化（Monomorphization）流水线、Java 风格类型擦除（Type Erasure）与桥接方法（Bridge Method）的运行时开销，以及 Swift/Go 采用的字典传递与目击表（Witness Table）混合架构。

表达式双向类型检查体系与上下文约束传播
--------------------------------------

在遍历抽象语法树进行语义验证时，朴素的自底向上（Bottom-Up）类型推导无法处理包含重载字面量、匿名 Lambda 闭包或泛型调用参数的语法结构。现代编译器普遍采用 **双向类型检查（Bidirectional Type Checking）** 架构，将类型分析解耦为两种相互交织的判定模式：

1. **类型综合模式（Synthesis / Infer Mode, $\Gamma \vdash e \Rightarrow 	au$）**：自底向上从表达式 $e$ 内部的结构与子节点属性直接推导出其确切类型 $	au$。适用于整型字面量、局部变量引用、字段寻址与显式强转表达式。
2. **类型校验模式（Checking Mode, $\Gamma \vdash e \Leftarrow 	au$）**：自顶向下将父节点或语法上下文期望的类型 $	au$ 压入当前表达式 $e$，验证 $e$ 是否能够满足该类型约束。适用于函数实参传递、变量初始化赋值、分支返回语句以及无显式类型标注的 Lambda 表达式。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                双向类型检查 (Bidirectional Type Checking) 数据流             |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 顶层语句上下文 ] : let target: f64 = expr;                              |
   |                                                                             |
   |   1. 校验模式下推 (Checking Mode):                                          |
   |      TypeChecker::check(expr, ExpectedType = f64)                           |
   |           |                                                                 |
   |           v                                                                 |
   |   [ 二元表达式节点 ] : expr = BinaryOp('+', Var(a: i32), Var(b: i32))       |
   |                                                                             |
   |   2. 综合模式推导 (Synthesis Mode):                                         |
   |      TypeChecker::synthesize(Var(a)) => i32                                 |
   |      TypeChecker::synthesize(Var(b)) => i32                                 |
   |      OpRule('+', i32, i32) => SynthesizedType = i32                         |
   |           |                                                                 |
   |           v                                                                 |
   |   3. 校验与转换协调 (Subtyping / Coercion Resolution):                      |
   |      验证 SynthesizedType (i32) 是否满足 ExpectedType (f64)                 |
   |      -> 命中数值提升规则 (Numeric Promotion)                                |
   |      -> 在 AST 中插入隐式转换节点: ImplicitCastExpr(i32 -> f64, expr)        |
   |      -> 交付满足约束的带类型 AST 节点                                       |
   |                                                                             |
   +-----------------------------------------------------------------------------+

表达式类型的局部判定表与上下文传递
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

表达式类型检查器以声明环境 $\Gamma$ 为输入，遍历表达式的各子节点并根据操作符类别执行规则匹配：

- **二元算术运算（Binary Arithmetic）**：针对算子 $\odot \in \{+, -, *, /, \%\}$，先分别综合左子树类型 $	au_L$ 与右子树类型 $	au_R$。若 $	au_L \equiv 	au_R$ 且属于标量数值集合，结果类型为 $	au_L$；若两端类型不一致，则触发类型提升决议（Promotion Resolution）。
- **关系与逻辑运算（Relational & Logical）**：针对算子 $\odot \in \{<, \le, >, \ge, ==, !=\}$，要求两端操作数满足可比性约束，结果类型固定综合为目标平台的布尔类型 ``bool``（在底层通常表现为 1 字节整数 ``i1`` 或 ``i8``）。
- **复合结构字段寻址（Field Access, ``obj.field``）**：首先综合接收者表达式类型 $	au_{	ext{recv}}$。若 $	au_{	ext{recv}}$ 为名义或结构体类型，在符号表中查找字段标识符，计算其内存相对基址的字节偏移量（Byte Offset）并返回字段声明类型；若字段不存在，终止推导并抛出语义诊断。
- **函数调用（Function Call, ``callee(arg_1, ..., arg_n)``）**：首先综合被调用者类型 $	au_{	ext{callee}}$。验证 $	au_{	ext{callee}}$ 必须具有函数签名形制 $(T_1, \dots, T_n) 	o T_{	ext{ret}}$。随后对每一个实参表达式 $	ext{arg}_i$ 在期望类型 $T_i$ 下执行校验模式检查（Checking Mode）。全部匹配成功后，调用表达式的结果类型确定为 $T_{	ext{ret}}$。

隐式类型转换、数值截断与寄存器级物理行为
----------------------------------------

在源码层面，程序员经常书写混合精度的算术表达式（如 ``float_val + int_val``）或将宽位宽整数赋值给窄位宽变量。编译器在类型检查阶段绝不能仅将失配作为静态错误拦截，而必须根据语言标准的数值转换分级表，在 AST 中显式构造 **隐式转换节点（``ImplicitCastExpr``）**，直接指导后端发射正确的硬件汇编指令。

数值提升与扩展：SExt 与 ZExt
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当较窄位宽的整型变量提升为较宽位宽整型变量时（如 8-bit ``i8`` 或 16-bit ``i16`` 扩展为 32-bit ``i32`` 或 64-bit ``i64``），硬件必须决定如何填充高位寄存器：

1. **符号扩展（Sign Extension, ``SExt``）**：适用于有符号整数（Signed Integers，二进制补码表示）。硬件将源操作数的最高有效位（Sign Bit，符号位）直接复制并填充至目标寄存器的所有高位空间。在 x86-64 架构下，对应指令为 ``MOVSX``（Move with Sign-Extension）或 ``MOVSXD``（将 32 位符号扩展至 64 位寄存器，例如 ``movsxd %edi, %rax``）；在 LLVM IR 中对应 ``sext i32 %val to i64`` 指令。
2. **零扩展（Zero Extension, ``ZExt``）**：适用于无符号整数（Unsigned Integers）。硬件将目标寄存器的所有高位直接清零。在 x86-64 架构下，对应指令为 ``MOVZX``（Move with Zero-Extension，例如 ``movzx %al, %eax``）；在 LLVM IR 中对应 ``zext i8 %val to i32`` 指令。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |             8-bit 到 16-bit 整数扩展在 CPU 物理寄存器中的位模式流转          |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 源 8-bit 寄存器 (%al) ] : 0b10000001 (无符号: 129, 有符号补码: -127)    |
   |                                                                             |
   |   1. 符号扩展 (SExt / MOVSX %al, %ax):                                      |
   |      符号位 (Bit 7) 为 1 -> 高 8 位全部填充 1                                |
   |      目标 16-bit 寄存器 (%ax): [ 11111111 ] [ 10000001 ]                     |
   |      数值保持: -127                                                         |
   |                                                                             |
   |   2. 零扩展 (ZExt / MOVZX %al, %ax):                                        |
   |      高 8 位全部清零                                                         |
   |      目标 16-bit 寄存器 (%ax): [ 00000000 ] [ 10000001 ]                     |
   |      数值保持: 129                                                          |
   |                                                                             |
   +-----------------------------------------------------------------------------+

数值截断（Truncation）与硬件溢出
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当宽位宽数据强制转换或隐式收窄为窄位宽数据时（如 64-bit ``i64`` 截断为 32-bit ``i32`` 或 8-bit ``i8``），编译器插入截断节点（在 LLVM IR 中为 ``trunc i64 %val to i32``）。

硬件层面的截断操作直接丢弃高位字节，仅保留低位物理寄存器（例如从 ``%rax`` 截断至 ``%eax`` 或 ``%al``）。截断操作具有以下物理副作用：
- **有效数据丢失**：若源数据的值域超出目标类型的表达范围（如将整数 300 截断为 8-bit 无符号整数 ``uint8``），$300 = 0x012C$，高位 $0x01$ 丢弃后仅保留 $0x2C = 44$，产生模 $2^8$ 环形回绕。
- **符号反转**：正数截断后若剩余位模式的最高位为 1，解释为有符号数时将突变为负数。
- **状态标志位（EFLAGS / RFLAGS）不受影响**：常规的寄存器间低位截断移动不会触发 CPU 硬件溢出中断，因此该语义风险必须由编译器在前端语义检查阶段通过显式警告或插入溢出边界检查代码予以控制。

浮点与整型相互转换
~~~~~~~~~~~~~~~~~~

浮点数（IEEE 754 格式：符号位 + 指数位 + 尾数位）与整型二进制补码之间无法通过简单的位移或位拷贝完成转换，必须依赖硬件浮点转换单元发射专门的微架构微码指令：
- **整型转浮点（Integer to FP）**：将补码整数正规化为科学计数法，计算指数偏移并舍入尾数。在 x86-64 中使用 SSE 指令 ``CVTSI2SD``（Convert Signed Doubleword Integer to Scalar Double-Precision Floating-Point）；在 LLVM IR 中对应 ``sitofp i32 %val to double``。
- **浮点转整型（FP to Integer）**：向零截断舍入浮点小数部分并写入整型寄存器。在 x86-64 中使用 ``CVTTSD2SI``（Convert with Truncation Scalar Double-Precision Floating-Point to Signed Doubleword Integer）；在 LLVM IR 中对应 ``fptosi double %val to i32``。

.. list-table:: 典型隐式转换在编译器中间表示与硬件指令集的映射
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 转换路径
     - 语义行为与位模式改变
     - LLVM IR 操作指令
     - x86-64 目标汇编指令
   * - ``i8`` $	o$ ``i32`` (有符号)
     - 符号位高位全量复制填充
     - ``sext i8 %x to i32``
     - ``movsbl %al, %eax``
   * - ``u8`` $	o$ ``u32`` (无符号)
     - 高 24 位物理清零
     - ``zext i8 %x to i32``
     - ``movzbl %al, %eax``
   * - ``i64`` $	o$ ``i32`` (截断)
     - 丢弃高 32 位，保留低 32 位
     - ``trunc i64 %x to i32``
     - ``movl %eax, %eax`` (低位直接寻址)
   * - ``i32`` $	o$ ``f64`` (浮点提升)
     - 标量整数转双精度 IEEE 754
     - ``sitofp i32 %x to double``
     - ``cvtsi2sd %edi, %xmm0``
   * - ``f64`` $	o$ ``i32`` (浮点截断)
     - 双精度浮点向零舍入取整
     - ``fptosi double %x to i32``
     - ``cvttsd2si %xmm0, %eax``

泛型与参数化多态的形式化模型
----------------------------

参数化多态（Parametric Polymorphism）允许一段算法或数据结构在定义时不绑定具体的物理数据类型，而是将类型作为参数进行抽象（Type-Level Abstraction），在实例化时再绑定具体类型实参。

在形式化类型论中，参数化多态的标准理论模型为 **二阶 Lambda 演算（System F / $\lambda 2$）**：
- **通用类型量化（Universal Quantification, $\forall X. 	au$）**：表示对任意类型 $X$，表达式均具备类型 $	au$。例如通用恒等函数 $	ext{id} = \Lambda X. \lambda x:X. x$，其类型为 $\forall X. X 	o X$。
- **类型应用（Type Application, $e [	au]$）**：将具体类型 $	au$ 代入类型抽象中，生成具体特化的函数类型，例如 $	ext{id} [	ext{i32}] = \lambda x:	ext{i32}. x$，其类型为 $	ext{i32} 	o 	ext{i32}$。

泛型约束（Generic Bounds / Concepts）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

完全无约束的泛型参数只能执行不依赖类型具体特征的操作（如指针搬运、容器存储、参数传递）。当泛型函数体需要对类型参数执行加法运算、比较操作或字段访问时，必须引入形式化约束：
- **C++ Concepts / Requires 表达式**：在编译期验证类型实参是否满足特定语法表达式与操作符重载集合。
- **Rust Trait Bounds**：形式化为 $\forall T: 	ext{Ord} + 	ext{Display}. \dots$，要求类型 $T$ 必须在全局符号表中注册对应 Trait 的虚表或实现块。
- **Java Bounded Generics**：形式化为 $\langle T 	ext{ extends Comparable}\langle T \rangle \rangle$，将类型变量的有界上界（Upper Bound）固定为目标接口。

泛型落盘实现双范式：单态化 vs 类型擦除
--------------------------------------

在完成泛型定义的语法与语义合法性检查后，编译器的中后端管线面临关键的分水岭：如何在底层目标机器码或虚拟机字节码中表示泛型？工业界形成了两种截然不同的物理实现路线。

路线一：单态化 (Monomorphization) —— 零运行时抽象成本
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

单态化（以 C++ 模板、Rust 泛型、Zig 为代表）将泛型视为编译期的代码生成器。编译器在前端记录泛型函数或结构体的 AST 原型。每当在调用点发现一组全新的具体类型实参组合时，编译器执行以下流水线：

1. **调用点类型实参收集与推导**：从调用实参中推导出未显式指定的类型实参（如 ``min(3_i32, 5_i32)`` 推导出 $T = 	ext{i32}$）。
2. **实例化请求去重与查询**：在全局实例化缓存表（Instantiation Map）中查询 Key: ``(GenericDeclId, [TypeArgs...])``。若已存在对应特化实例，直接返回其符号；若不存在，将其压入待编译特化工作队列。
3. **AST / HIR 深度克隆与符号替换**：克隆泛型原型的完整 AST 树，遍历所有子节点，将类型变量引用递归替换为具体的物理类型（如将所有 $T$ 替换为 $	ext{i32}$）。
4. **符号修饰与重整（Name Mangling）**：依据 ABI 规范（如 Itanium C++ ABI），将泛型名与具体类型签名编码为全局唯一的链接符号名称（例如 ``min<int>`` 重整为 ``_Z3minIiET_S0_S0_``，``min<double>`` 重整为 ``_Z3minIdET_S0_S0_``）。
5. **独立发射机器码与二次语义检查**：对特化后的 AST 执行完整的代码生成，生成针对目标类型尺寸与对齐专门优化的机器码。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                泛型单态化 (Monomorphization) 编译期特化流转                  |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 泛型源码原型 ] : template<typename T> T min(T a, T b) { return a < b ? a : b; }
   |            |                                                                |
   |            +--------------------------------+                               |
   |            | 调用点 1: min(10, 20)           | 调用点 2: min(1.5, 2.5)       |
   |            v                                v                               |
   |   [ 推导实参 ]: T = i32            [ 推导实参 ]: T = f64                    |
   |            |                                |                               |
   |            v                                v                               |
   |   [ AST 克隆与类型代换 ]           [ AST 克隆与类型代换 ]                   |
   |   i32 min_i32(i32 a, i32 b)        f64 min_f64(f64 a, f64 b)                |
   |            |                                |                               |
   |            v                                v                               |
   |   [ 符号重整 (Mangling) ]          [ 符号重整 (Mangling) ]                  |
   |   _Z3minIiET_S0_S0_                _Z3minIdET_S0_S0_                        |
   |            |                                |                               |
   |            v                                v                               |
   |   [ 目标机器码发射: 专用 ALU 指令 ]  [ 目标机器码发射: 专用 SSE/FPU 指令 ]    |
   |   cmovl %esi, %edi (寄存器整型比较)   ucomisd %xmm1, %xmm0 (浮点比较指令)     |
   |                                                                             |
   +-----------------------------------------------------------------------------+

**物理优势**：
- **零运行时开销**：消除所有间接寻址、虚表查找与动态类型分支。
- **极致内联与深度优化**：后端优化器（LLVM / GCC）面对的是完全展开的常规函数，可以对其执行常量折叠、循环展开、死代码消除以及 SIMD 自动向量化。
- **无装箱开销**：基础标量类型（``i32``、``f64``）直接保存在 CPU 通用寄存器或向量寄存器中，数据结构紧凑连续排布，缓存命中率极高。

**工程代价**：
- **代码体积膨胀（Code Bloat）**：同一个泛型函数若被 50 种不同类型调用，将在目标二进制文件中生成 50 份完全独立的机器指令副本，导致指令缓存（I-Cache）失效。
- **编译时间剧增**：每次特化都需要重新经历完整的 IR 生成、优化与寄存器分配。
- **跨动态链接库（DSO）共享困难**：泛型实现必须暴露在头文件或元数据包中，无法做到预编译二进制解耦。

路线二：类型擦除 (Type Erasure) —— 共享通用字节码
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

类型擦除（以 Java、TypeScript、早期 C# 为代表）将类型参数仅用于前端静态类型安全验证。一旦类型检查完成，编译器在向字节码或底层运行时降级时，将所有类型参数从 AST 中完全抹除：

1. **类型变量上界替换**：将所有的类型参数 $T$ 替换为其声明的最顶层上界（Upper Bound）。无界类型变量直接替换为根对象类型（如 Java 中的 ``java.lang.Object``，TypeScript 中直接剔除类型注解）。
2. **强制类型转换注入（Downcast Insertion）**：在泛型方法的调用点和返回值接收处，由编译器自动合成向下类型转换字节码指令（在 JVM 字节码中对应 ``checkcast`` 指令）。
3. **合成桥接方法（Synthetic Bridge Method）**：当子类继承泛型父类或实现泛型接口并指定具体类型时，编译器自动在子类虚表（vtable）中合成一个签名包含 ``Object`` 的桥接函数，内部转发给具体类型实现，以确保面向对象多态虚分发机制的完整性。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                    Java 风格类型擦除 (Type Erasure) 流转                     |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 源码泛型定义 ] : class Box<T> { T val; T get() { return val; } }        |
   |            |                                                                |
   |            v                                                                |
   |   [ 类型擦除后字节码 ]: class Box { Object val; Object get() { return val; } }|
   |                                                                             |
   |   [ 调用点源码 ]: Box<String> box = ...; String s = box.get();              |
   |            |                                                                |
   |            v (编译器自动在字节码中注入运行时类型检查与强转)                 |
   |   [ 生成字节码 ]:                                                           |
   |     invokevirtual Box.get()Ljava/lang/Object;                               |
   |     checkcast java/lang/String   <-- 插入的类型检查与强转指令               |
   |     astore_1                                                                |
   |                                                                             |
   +-----------------------------------------------------------------------------+

**物理代价**：
- **装箱与拆箱（Boxing & Unboxing）**：为了让基础数据类型（如 ``int``、``double``）能够作为 ``Object`` 传递，必须将其封装在堆分配的对象中（如 ``java.lang.Integer``）。导致频繁触发堆内存分配（Heap Allocation）、垃圾回收压力（GC Pressure）以及额外的指针间接解引用。
- **运行时类型信息丢失**：在运行时无法通过反射直接获取 $T$ 的具体物理类型（例如无法直接执行 ``new T()`` 或 ``new T[10]``）。

混合范式：字典传递与目击表 (Dictionary Passing & Witness Tables)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了兼顾代码体积与对基础类型的无装箱支持，Swift、Go、Haskell 等语言引入了 **字典传递（Dictionary Passing）** 机制：

- 编译器不为每个具体类型生成全部重复的代码副本，而是编译生成一份统一的泛型函数机器码。
- 在调用该泛型函数时，调用方额外向函数隐式传递一个隐藏参数——**类型元数据字典（Type Metadata Dictionary / Protocol Witness Table）**。
- 该字典中包含了对应类型在目标平台上的物理几何尺寸（Size）、对齐方式（Alignment）、内存拷贝/移动函数指针以及具体方法实现的函数指针。泛型函数内部通过该字典以动态栈偏移与间接调用的方式操作数据。

.. list-table:: 泛型实现三大范式（单态化、类型擦除、字典传递）工程特性对比
   :widths: 18 28 27 27
   :header-rows: 1
   :class: tight-table

   * - 评价维度
     - 单态化 (Monomorphization)
     - 类型擦除 (Type Erasure)
     - 字典传递 (Witness Tables)
   * - 典型代表实现
     - C++ Templates, Rust, Zig
     - Java, Kotlin, TypeScript
     - Swift (Generics), Go (interface), Haskell
   * - 机器码形态
     - 每种类型实参生成独立专用机器码
     - 全局共享一份擦除为通用对象的代码
     - 共享一份通用代码，运行时接收元数据字典
   * - 基础标量类型支持
     - 原生零成本支持，寄存器直接传递
     - 必须装箱为堆对象 (Boxing/Heap)
     - 原生支持，通过值目击表动态分配栈槽
   * - 二进制文件体积
     - 显著膨胀 (Code Bloat)
     - 极度紧凑，无重复字节码
     - 紧凑，仅增加少量元数据字典表格
   * - 运行时执行性能
     - 极高（零间接层，完全支持内联与 SIMD）
     - 中等（存在类型检查与装箱解引用）
     - 良好（存在少许字典读取与间接函数调用）
   * - 编译构建耗时
     - 漫长（需特化、重复优化所有实例）
     - 迅速（仅需单遍编译与简单标记）
     - 较快（生成统一 IR 与元数据结构）
   * - 运行时类型可见性
     - 完全透明且物理特化
     - 类型被擦除，反射需借助元数据标签
     - 完全保留运行时具体类型描述符

工业级 C++ 表达式类型检查与泛型单态化特化引擎实现
--------------------------------------------------

以下源码实现了一个自包含且工业级完整的编译器语义分析子系统。该引擎涵盖：
1. 具备完整继承拓扑的 AST 表达式体系（包含字面量、变量引用、二元运算、函数调用、隐式类型转换节点 ``ImplicitCastExpr`` 以及泛型函数声明）。
2. 支持综合（Synthesis）与校验（Checking）的双向类型检查器，实现整型自动提升、符号扩展、零扩展以及截断节点的自动识别与 AST 树结构改写。
3. 完整的泛型单态化（Monomorphization）实例化管道：支持类型实参推导、泛型 AST 递归深拷贝与类型替换（Substitution）、符号修饰（Name Mangling）以及特化实例的二次语义验证。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <unordered_map>
   #include <algorithm>
   #include <cstdint>
   #include <cassert>
   #include <sstream>

   // =========================================================================
   // 1. 类型系统基础数据结构
   // =========================================================================
   enum class BaseTypeKind : uint8_t {
       Void,
       Bool,
       Int8,
       Int32,
       Int64,
       Float64,
       TypeVar,     // 泛型类型变量 (如 T, U)
       Function     // 函数类型
   };

   enum class CastKind : uint8_t {
       NoOp,             // 无操作
       IntegralSExt,     // 有符号整型符号扩展 (e.g. i8 -> i32)
       IntegralZExt,     // 无符号整型零扩展
       IntegralTrunc,    // 整型截断 (e.g. i64 -> i32)
       IntToFloat,       // 整数提升为浮点数 (e.g. i32 -> f64)
       FloatToInt        // 浮点截断为整数 (e.g. f64 -> i32)
   };

   struct Type {
       BaseTypeKind Kind;
       std::string Name;
       uint32_t SizeBytes = 0;
       bool IsSigned = true;

       // 用于 Function 类型
       std::vector<const Type*> ParamTypes;
       const Type *ReturnType = nullptr;

       bool isInteger() const {
           return Kind == BaseTypeKind::Int8 || Kind == BaseTypeKind::Int32 || Kind == BaseTypeKind::Int64;
       }
       bool isFloat() const {
           return Kind == BaseTypeKind::Float64;
       }
       bool isTypeVar() const {
           return Kind == BaseTypeKind::TypeVar;
       }
       bool isFunction() const {
           return Kind == BaseTypeKind::Function;
       }
   };

   // 全局类型注册池
   class TypePool {
   public:
       TypePool() {
           VoidTy = createPrimitive(BaseTypeKind::Void, "void", 0, false);
           BoolTy = createPrimitive(BaseTypeKind::Bool, "bool", 1, false);
           Int8Ty = createPrimitive(BaseTypeKind::Int8, "i8", 1, true);
           Int32Ty = createPrimitive(BaseTypeKind::Int32, "i32", 4, true);
           Int64Ty = createPrimitive(BaseTypeKind::Int64, "i64", 8, true);
           Float64Ty = createPrimitive(BaseTypeKind::Float64, "f64", 8, true);
       }

       const Type* getVoid() const { return VoidTy; }
       const Type* getBool() const { return BoolTy; }
       const Type* getInt8() const { return Int8Ty; }
       const Type* getInt32() const { return Int32Ty; }
       const Type* getInt64() const { return Int64Ty; }
       const Type* getFloat64() const { return Float64Ty; }

       const Type* createTypeVar(const std::string &name) {
           return createPrimitive(BaseTypeKind::TypeVar, name, 0, false);
       }

       const Type* createFunctionType(std::vector<const Type*> params, const Type *ret) {
           AllocatedTypes.push_back(std::make_unique<Type>());
           Type *t = AllocatedTypes.back().get();
           t->Kind = BaseTypeKind::Function;
           t->ParamTypes = std::move(params);
           t->ReturnType = ret;
           std::stringstream ss;
           ss << "(";
           for (size_t i = 0; i < t->ParamTypes.size(); ++i) {
               if (i > 0) ss << ", ";
               ss << t->ParamTypes[i]->Name;
           }
           ss << ") -> " << ret->Name;
           t->Name = ss.str();
           return t;
       }

   private:
       const Type* createPrimitive(BaseTypeKind kind, std::string name, uint32_t size, bool isSigned) {
           AllocatedTypes.push_back(std::make_unique<Type>());
           Type *t = AllocatedTypes.back().get();
           t->Kind = kind;
           t->Name = std::move(name);
           t->SizeBytes = size;
           t->IsSigned = isSigned;
           return t;
       }

       const Type *VoidTy;
       const Type *BoolTy;
       const Type *Int8Ty;
       const Type *Int32Ty;
       const Type *Int64Ty;
       const Type *Float64Ty;
       std::vector<std::unique_ptr<Type>> AllocatedTypes;
   };

   // =========================================================================
   // 2. 抽象语法树 (AST) 节点层级拓扑
   // =========================================================================
   enum class ASTNodeKind {
       IntegerLiteral,
       FloatLiteral,
       VariableRef,
       BinaryExpr,
       ImplicitCastExpr,
       CallExpr,
       GenericFunctionDecl,
       SpecializedFunctionDecl
   };

   struct ASTNode {
       virtual ~ASTNode() = default;
       virtual ASTNodeKind getKind() const = 0;
       const Type *InferredType = nullptr; // 语义推导出的结果类型
       virtual std::unique_ptr<ASTNode> clone() const = 0; // 支持泛型单态化深度克隆
   };

   struct IntegerLiteralNode : public ASTNode {
       int64_t Value;
       IntegerLiteralNode(int64_t val, const Type *ty) : Value(val) { InferredType = ty; }
       ASTNodeKind getKind() const override { return ASTNodeKind::IntegerLiteral; }
       std::unique_ptr<ASTNode> clone() const override {
           return std::make_unique<IntegerLiteralNode>(Value, InferredType);
       }
   };

   struct FloatLiteralNode : public ASTNode {
       double Value;
       FloatLiteralNode(double val, const Type *ty) : Value(val) { InferredType = ty; }
       ASTNodeKind getKind() const override { return ASTNodeKind::FloatLiteral; }
       std::unique_ptr<ASTNode> clone() const override {
           return std::make_unique<FloatLiteralNode>(Value, InferredType);
       }
   };

   struct VariableRefNode : public ASTNode {
       std::string VarName;
       VariableRefNode(std::string name) : VarName(std::move(name)) {}
       ASTNodeKind getKind() const override { return ASTNodeKind::VariableRef; }
       std::unique_ptr<ASTNode> clone() const override {
           auto node = std::make_unique<VariableRefNode>(VarName);
           node->InferredType = InferredType;
           return node;
       }
   };

   struct ImplicitCastExpr : public ASTNode {
       CastKind ConversionKind;
       std::unique_ptr<ASTNode> SubExpr;

       ImplicitCastExpr(CastKind kind, std::unique_ptr<ASTNode> sub, const Type *destType)
           : ConversionKind(kind), SubExpr(std::move(sub)) {
           InferredType = destType;
       }
       ASTNodeKind getKind() const override { return ASTNodeKind::ImplicitCastExpr; }
       std::unique_ptr<ASTNode> clone() const override {
           return std::make_unique<ImplicitCastExpr>(ConversionKind, SubExpr->clone(), InferredType);
       }
   };

   enum class BinaryOpKind { Add, Sub, Mul, Div, LessThan, Equal };

   struct BinaryExprAST : public ASTNode {
       BinaryOpKind Op;
       std::unique_ptr<ASTNode> LHS;
       std::unique_ptr<ASTNode> RHS;

       BinaryExprAST(BinaryOpKind op, std::unique_ptr<ASTNode> lhs, std::unique_ptr<ASTNode> rhs)
           : Op(op), LHS(std::move(lhs)), RHS(std::move(rhs)) {}

       ASTNodeKind getKind() const override { return ASTNodeKind::BinaryExpr; }
       std::unique_ptr<ASTNode> clone() const override {
           auto node = std::make_unique<BinaryExprAST>(Op, LHS->clone(), RHS->clone());
           node->InferredType = InferredType;
           return node;
       }
   };

   struct CallExprAST : public ASTNode {
       std::string CalleeName;
       std::vector<std::unique_ptr<ASTNode>> Args;

       CallExprAST(std::string callee, std::vector<std::unique_ptr<ASTNode>> args)
           : CalleeName(std::move(callee)), Args(std::move(args)) {}

       ASTNodeKind getKind() const override { return ASTNodeKind::CallExpr; }
       std::unique_ptr<ASTNode> clone() const override {
           std::vector<std::unique_ptr<ASTNode>> clonedArgs;
           for (const auto &arg : Args) clonedArgs.push_back(arg->clone());
           auto node = std::make_unique<CallExprAST>(CalleeName, std::move(clonedArgs));
           node->InferredType = InferredType;
           return node;
       }
   };

   struct GenericFunctionDecl : public ASTNode {
       std::string Name;
       std::vector<std::string> TypeParams; // e.g. {"T"}
       std::vector<std::pair<std::string, const Type*>> Params; // e.g. {"a", T}, {"b", T}
       const Type *ReturnType;
       std::unique_ptr<ASTNode> Body;

       GenericFunctionDecl(std::string name, std::vector<std::string> tparams,
                           std::vector<std::pair<std::string, const Type*>> params,
                           const Type *ret, std::unique_ptr<ASTNode> body)
           : Name(std::move(name)), TypeParams(std::move(tparams)),
             Params(std::move(params)), ReturnType(ret), Body(std::move(body)) {}

       ASTNodeKind getKind() const override { return ASTNodeKind::GenericFunctionDecl; }
       std::unique_ptr<ASTNode> clone() const override {
           return std::make_unique<GenericFunctionDecl>(
               Name, TypeParams, Params, ReturnType, Body ? Body->clone() : nullptr);
       }
   };

   struct SpecializedFunctionDecl : public ASTNode {
       std::string MangledName;
       std::vector<std::pair<std::string, const Type*>> Params;
       const Type *ReturnType;
       std::unique_ptr<ASTNode> Body;

       SpecializedFunctionDecl(std::string mangledName,
                               std::vector<std::pair<std::string, const Type*>> params,
                               const Type *ret, std::unique_ptr<ASTNode> body)
           : MangledName(std::move(mangledName)), Params(std::move(params)),
             ReturnType(ret), Body(std::move(body)) {}

       ASTNodeKind getKind() const override { return ASTNodeKind::SpecializedFunctionDecl; }
       std::unique_ptr<ASTNode> clone() const override {
           return std::make_unique<SpecializedFunctionDecl>(
               MangledName, Params, ReturnType, Body ? Body->clone() : nullptr);
       }
   };

   // =========================================================================
   // 3. 双向类型检查与隐式转换注入器 (Bidirectional Type Checker)
   // =========================================================================
   class TypeChecker {
   public:
       TypeChecker(TypePool &pool) : Types(pool) {}

       void registerSymbol(const std::string &name, const Type *ty) {
           ScopeSymbolTable[name] = ty;
       }

       // 综合模式: 推导表达式类型 (Synthesis Mode)
       const Type* synthesizeType(std::unique_ptr<ASTNode> &node) {
           if (!node) return Types.getVoid();

           switch (node->getKind()) {
               case ASTNodeKind::IntegerLiteral:
               case ASTNodeKind::FloatLiteral:
                   return node->InferredType;

               case ASTNodeKind::VariableRef: {
                   auto *var = static_cast<VariableRefNode*>(node.get());
                   auto it = ScopeSymbolTable.find(var->VarName);
                   assert(it != ScopeSymbolTable.end() && "未声明的标识符引用");
                   node->InferredType = it->second;
                   return node->InferredType;
               }

               case ASTNodeKind::BinaryExpr: {
                   auto *bin = static_cast<BinaryExprAST*>(node.get());
                   const Type *lhsTy = synthesizeType(bin->LHS);
                   const Type *rhsTy = synthesizeType(bin->RHS);

                   // 若左右类型失配，尝试插入隐式类型提升转换 (Coercion)
                   if (lhsTy != rhsTy) {
                       if (lhsTy->isInteger() && rhsTy->isFloat()) {
                           // LHS 提升为 Float64
                           bin->LHS = std::make_unique<ImplicitCastExpr>(
                               CastKind::IntToFloat, std::move(bin->LHS), Types.getFloat64());
                           lhsTy = Types.getFloat64();
                       } else if (lhsTy->isFloat() && rhsTy->isInteger()) {
                           // RHS 提升为 Float64
                           bin->RHS = std::make_unique<ImplicitCastExpr>(
                               CastKind::IntToFloat, std::move(bin->RHS), Types.getFloat64());
                           rhsTy = Types.getFloat64();
                       } else if (lhsTy->isInteger() && rhsTy->isInteger()) {
                           // 整数位宽对齐 (小位宽向大位宽提升)
                           if (lhsTy->SizeBytes < rhsTy->SizeBytes) {
                               bin->LHS = std::make_unique<ImplicitCastExpr>(
                                   CastKind::IntegralSExt, std::move(bin->LHS), rhsTy);
                               lhsTy = rhsTy;
                           } else {
                               bin->RHS = std::make_unique<ImplicitCastExpr>(
                                   CastKind::IntegralSExt, std::move(bin->RHS), lhsTy);
                               rhsTy = lhsTy;
                           }
                       }
                   }

                   // 判定二元运算的结果类型
                   if (bin->Op == BinaryOpKind::LessThan || bin->Op == BinaryOpKind::Equal) {
                       bin->InferredType = Types.getBool();
                   } else {
                       bin->InferredType = lhsTy;
                   }
                   return bin->InferredType;
               }

               case ASTNodeKind::ImplicitCastExpr:
                   return node->InferredType;

               default:
                   break;
           }
           return Types.getVoid();
       }

       // 校验模式: 验证表达式满足期望类型，必要时直接注入 Cast 节点 (Checking Mode)
       void checkType(std::unique_ptr<ASTNode> &node, const Type *expectedType) {
           const Type *actualTy = synthesizeType(node);
           if (actualTy == expectedType) return;

           // 执行转换注入
           if (actualTy->isInteger() && expectedType->isFloat()) {
               node = std::make_unique<ImplicitCastExpr>(CastKind::IntToFloat, std::move(node), expectedType);
           } else if (actualTy->isInteger() && expectedType->isInteger()) {
               if (actualTy->SizeBytes < expectedType->SizeBytes) {
                   node = std::make_unique<ImplicitCastExpr>(CastKind::IntegralSExt, std::move(node), expectedType);
               } else if (actualTy->SizeBytes > expectedType->SizeBytes) {
                   node = std::make_unique<ImplicitCastExpr>(CastKind::IntegralTrunc, std::move(node), expectedType);
               }
           } else if (actualTy->isFloat() && expectedType->isInteger()) {
               node = std::make_unique<ImplicitCastExpr>(CastKind::FloatToInt, std::move(node), expectedType);
           } else {
               std::cerr << "[类型检查错误] 无法将类型 " << actualTy->Name << " 转换为期望类型 " << expectedType->Name << "
";
               assert(false && "类型系统校验失败");
           }
       }

   private:
       TypePool &Types;
       std::unordered_map<std::string, const Type*> ScopeSymbolTable;
   };

   // =========================================================================
   // 4. 泛型单态化特化引擎 (Monomorphizer)
   // =========================================================================
   class Monomorphizer {
   public:
       Monomorphizer(TypePool &pool) : Types(pool) {}

       // 注册泛型函数原型
       void registerGenericFunction(std::unique_ptr<GenericFunctionDecl> decl) {
           GenericRegistry[decl->Name] = std::move(decl);
       }

       // 符号重整算法 (Itanium ABI 风格缩微实现)
       std::string mangleName(const std::string &baseName, const std::vector<const Type*> &typeArgs) {
           std::stringstream ss;
           ss << "_Z" << baseName.length() << baseName;
           if (!typeArgs.empty()) {
               ss << "I";
               for (const auto *ty : typeArgs) {
                   if (ty->Kind == BaseTypeKind::Int8) ss << "a";
                   else if (ty->Kind == BaseTypeKind::Int32) ss << "i";
                   else if (ty->Kind == BaseTypeKind::Int64) ss << "l";
                   else if (ty->Kind == BaseTypeKind::Float64) ss << "d";
                   else if (ty->Kind == BaseTypeKind::Bool) ss << "b";
                   else ss << ty->Name.length() << ty->Name;
               }
               ss << "E";
           }
           return ss.str();
       }

       // 单态化实例化接口
       const SpecializedFunctionDecl* instantiate(const std::string &funcName,
                                                  const std::vector<const Type*> &typeArgs) {
           auto it = GenericRegistry.find(funcName);
           assert(it != GenericRegistry.end() && "未找到泛型函数声明");
           GenericFunctionDecl *proto = it->second.get();
           assert(proto->TypeParams.size() == typeArgs.size() && "泛型实参数量失配");

           std::string mangled = mangleName(funcName, typeArgs);
           auto specIt = Specializations.find(mangled);
           if (specIt != Specializations.end()) {
               return specIt->second.get(); // 命中断言缓存，直接复用已生成的特化实例
           }

           // 1. 构建类型代换映射表: TypeParamName -> ConcreteType
           std::unordered_map<std::string, const Type*> substMap;
           for (size_t i = 0; i < proto->TypeParams.size(); ++i) {
               substMap[proto->TypeParams[i]] = typeArgs[i];
           }

           // 2. 深度克隆函数体并执行类型代换 (AST Substitution)
           std::unique_ptr<ASTNode> specializedBody = proto->Body ? proto->Body->clone() : nullptr;
           if (specializedBody) {
               substituteTypes(specializedBody.get(), substMap);
           }

           // 3. 构建特化参数与返回类型
           std::vector<std::pair<std::string, const Type*>> specParams;
           for (const auto &p : proto->Params) {
               const Type *resolvedTy = resolveTypeSubstitution(p.second, substMap);
               specParams.push_back({p.first, resolvedTy});
           }
           const Type *specRet = resolveTypeSubstitution(proto->ReturnType, substMap);

           // 4. 对特化生成的 AST 执行二次类型检查与隐式转换注入
           TypeChecker localChecker(Types);
           for (const auto &p : specParams) {
               localChecker.registerSymbol(p.first, p.second);
           }
           if (specializedBody) {
               localChecker.checkType(specializedBody, specRet);
           }

           auto specDecl = std::make_unique<SpecializedFunctionDecl>(
               mangled, std::move(specParams), specRet, std::move(specializedBody));
           const auto *ptr = specDecl.get();
           Specializations[mangled] = std::move(specDecl);
           return ptr;
       }

   private:
       const Type* resolveTypeSubstitution(const Type *srcTy,
                                           const std::unordered_map<std::string, const Type*> &substMap) {
           if (srcTy->isTypeVar()) {
               auto it = substMap.find(srcTy->Name);
               if (it != substMap.end()) return it->second;
           }
           return srcTy;
       }

       void substituteTypes(ASTNode *node, const std::unordered_map<std::string, const Type*> &substMap) {
           if (!node) return;
           if (node->InferredType) {
               node->InferredType = resolveTypeSubstitution(node->InferredType, substMap);
           }

           switch (node->getKind()) {
               case ASTNodeKind::BinaryExpr: {
                   auto *bin = static_cast<BinaryExprAST*>(node);
                   substituteTypes(bin->LHS.get(), substMap);
                   substituteTypes(bin->RHS.get(), substMap);
                   break;
               }
               case ASTNodeKind::ImplicitCastExpr: {
                   auto *cast = static_cast<ImplicitCastExpr*>(node);
                   substituteTypes(cast->SubExpr.get(), substMap);
                   break;
               }
               default:
                   break;
           }
       }

       TypePool &Types;
       std::unordered_map<std::string, std::unique_ptr<GenericFunctionDecl>> GenericRegistry;
       std::unordered_map<std::string, std::unique_ptr<SpecializedFunctionDecl>> Specializations;
   };

   // =========================================================================
   // 5. 调试输出与 AST 树可视化
   // =========================================================================
   void printAST(const ASTNode *node, int indent = 0) {
       std::string pad(indent * 2, ' ');
       if (!node) {
           std::cout << pad << "<null>
";
           return;
       }

       switch (node->getKind()) {
           case ASTNodeKind::IntegerLiteral: {
               auto *lit = static_cast<const IntegerLiteralNode*>(node);
               std::cout << pad << "IntegerLiteral: " << lit->Value 
                         << " [Type: " << (lit->InferredType ? lit->InferredType->Name : "untyped") << "]
";
               break;
           }
           case ASTNodeKind::FloatLiteral: {
               auto *lit = static_cast<const FloatLiteralNode*>(node);
               std::cout << pad << "FloatLiteral: " << lit->Value 
                         << " [Type: " << (lit->InferredType ? lit->InferredType->Name : "untyped") << "]
";
               break;
           }
           case ASTNodeKind::VariableRef: {
               auto *var = static_cast<const VariableRefNode*>(node);
               std::cout << pad << "VariableRef: " << var->VarName 
                         << " [Type: " << (var->InferredType ? var->InferredType->Name : "untyped") << "]
";
               break;
           }
           case ASTNodeKind::ImplicitCastExpr: {
               auto *cast = static_cast<const ImplicitCastExpr*>(node);
               std::string castName = "Cast";
               if (cast->ConversionKind == CastKind::IntegralSExt) castName = "ImplicitCast<IntegralSExt>";
               else if (cast->ConversionKind == CastKind::IntegralTrunc) castName = "ImplicitCast<IntegralTrunc>";
               else if (cast->ConversionKind == CastKind::IntToFloat) castName = "ImplicitCast<IntToFloat>";
               std::cout << pad << castName << " -> " << cast->InferredType->Name << "
";
               printAST(cast->SubExpr.get(), indent + 1);
               break;
           }
           case ASTNodeKind::BinaryExpr: {
               auto *bin = static_cast<const BinaryExprAST*>(node);
               std::cout << pad << "BinaryExpr (Op: " << (bin->Op == BinaryOpKind::Add ? "+" : "<") 
                         << ") [Type: " << (bin->InferredType ? bin->InferredType->Name : "untyped") << "]
";
               printAST(bin->LHS.get(), indent + 1);
               printAST(bin->RHS.get(), indent + 1);
               break;
           }
           default:
               std::cout << pad << "ASTNode (Other)
";
               break;
       }
   }

   // =========================================================================
   // 6. 端到端主运行与验证测试
   // =========================================================================
   int main() {
       TypePool pool;
       TypeChecker checker(pool);
       Monomorphizer monomorphizer(pool);

       std::cout << "========================================================================
";
       std::cout << "现代编译器表达式双向类型检查、隐式转换注入与泛型单态化特化引擎
";
       std::cout << "========================================================================

";

       // ---------------------------------------------------------------------
       // 测试 1: 混合算术表达式的隐式类型提升与 Cast 节点自动插入
       // ---------------------------------------------------------------------
       std::cout << ">>> [测试 1] 混合算术表达式检查: (var_i8: i8 + var_i64: i64) 赋值给 f64
";
       checker.registerSymbol("var_i8", pool.getInt8());
       checker.registerSymbol("var_i64", pool.getInt64());

       // 构造 AST: var_i8 + var_i64
       std::unique_ptr<ASTNode> mixedExpr = std::make_unique<BinaryExprAST>(
           BinaryOpKind::Add,
           std::make_unique<VariableRefNode>("var_i8"),
           std::make_unique<VariableRefNode>("var_i64")
       );

       // 在期望类型 f64 下执行双向检查 (自底向上综合 + 自顶向下提升)
       checker.checkType(mixedExpr, pool.getFloat64());

       std::cout << "[转换完成] 生成的修饰 AST 树结构:
";
       printAST(mixedExpr.get(), 1);
       std::cout << "
";

       // ---------------------------------------------------------------------
       // 测试 2: 泛型函数原型定义与单态化特化 (Monomorphization)
       // ---------------------------------------------------------------------
       std::cout << ">>> [测试 2] 泛型函数单态化: template<T> T add(T a, T b) { return a + b; }
";
       const Type *typeVarT = pool.createTypeVar("T");

       auto genericAddBody = std::make_unique<BinaryExprAST>(
           BinaryOpKind::Add,
           std::make_unique<VariableRefNode>("a"),
           std::make_unique<VariableRefNode>("b")
       );

       auto genericAddDecl = std::make_unique<GenericFunctionDecl>(
           "add",
           std::vector<std::string>{"T"},
           std::vector<std::pair<std::string, const Type*>>{{"a", typeVarT}, {"b", typeVarT}},
           typeVarT,
           std::move(genericAddBody)
       );

       monomorphizer.registerGenericFunction(std::move(genericAddDecl));

       // 特化实例 1: add<i32>
       std::cout << "--> 触发特化实例化 1: add<i32>
";
       const auto *specI32 = monomorphizer.instantiate("add", {pool.getInt32()});
       std::cout << "    [符号重整结果] " << specI32->MangledName << "
";
       std::cout << "    [特化 AST 树结构]:
";
       printAST(specI32->Body.get(), 2);

       // 特化实例 2: add<f64>
       std::cout << "
--> 触发特化实例化 2: add<f64>
";
       const auto *specF64 = monomorphizer.instantiate("add", {pool.getFloat64()});
       std::cout << "    [符号重整结果] " << specF64->MangledName << "
";
       std::cout << "    [特化 AST 树结构]:
";
       printAST(specF64->Body.get(), 2);

       // 验证特化缓存复用
       std::cout << "
--> 再次调用 add<i32> (测试实例化缓存去重):
";
       const auto *specI32_Cached = monomorphizer.instantiate("add", {pool.getInt32()});
       std::cout << "    内存地址比对: " << (specI32 == specI32_Cached ? "相同 (命中全局特化缓存)" : "错误") << "

";

       return 0;
   }

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 引擎，输出日志验证了编译器处理类型检查与泛型特化的核心行为：

1. **双向数值扩展与提升协调**：在处理 ``var_i8 + var_i64`` 时，检查器首先在二元运算子节点检测到 8-bit 与 64-bit 失配，自动将 ``var_i8`` 包装进 ``ImplicitCast<IntegralSExt>`` 提升至 ``i64``，运算结果综合为 ``i64``。随后在外层 ``f64`` 期望约束下，再次将整个二元树包装进 ``ImplicitCast<IntToFloat>``，确保后端直接发射 ``CVTSI2SD`` 浮点指令。
2. **泛型 AST 深度克隆与类型代换**：单态化引擎成功将抽象占位符 ``T`` 分别代换为物理类型 ``i32`` 与 ``f64``，并正确生成符合 Itanium ABI 规则的唯一修饰符号 ``_Z3addIiE`` 与 ``_Z3addIdE``。
3. **全局实例化去重**：针对同一类型实参的重复调用精确命中缓存，杜绝重复代码生成。

小结与下章导读
--------------

本章系统解构了现代编译器在表达式层级进行类型语义验证、指令转换适配与泛型实例化的工程全貌：

1. **双向类型检查流水线**：将自底向上的综合模式与自顶向下的校验模式融合，实现了复杂上下文中类型约束的精准传递与局部推导。
2. **隐式转换的微架构映射**：深入剖析了符号扩展（``SExt`` / ``MOVSX``）、零扩展（``ZExt`` / ``MOVZX``）、截断（``Trunc``）以及浮点/整型转换在 CPU 物理寄存器与状态标志位上的真实行为，明确了显式插入 ``ImplicitCastExpr`` 节点的必要性。
3. **参数化多态的形式化表征**：依托 System F 类型抽象理论，阐明了类型变量替换与泛型约束求解的基础规则。
4. **单态化 vs 类型擦除 vs 字典传递**：横向对比了 C++/Rust（单态化特化、零运行时成本但存在代码膨胀）、Java（类型擦除、统一对象表示但引入装箱与桥接开销）以及 Swift/Go（字典传递、值目击表动态分配）在时间、空间与优化自由度上的物理权衡。

在目前讨论的类型系统中，所有变量与函数的类型签名均需要显式声明或通过简单的局部双向规则直接获得。然而，在以 ML、Haskell、Rust、TypeScript 以及现代 C++（``auto`` / ``decltype``）为代表的语言中，编译器具备在不提供显式类型注解的情况下自动推导出全局或局部任意复杂类型的能力。在第 3 模块第 5 节 **局部与全局类型推导：类型变量、方程约束收集与 Hindley-Milner / Unification 合一求解算法（03_semantic_analysis_and_type_systems/05_type_inference_and_unification_algorithms.rst）** 中，我们将深入剖析类型方程的自动化生成、基于 Robinson 合一算法（Unification Algorithm）的等式消解，以及 Hindley-Milner (HM / Algorithm W) 经典类型推导体系的形式化推导与工业级实现。
