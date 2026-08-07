第052章：Pointers, References, and Aliasing
===========================================

核心知识点
----------

* Aliasing 表示不同指针、引用或地址表达式可能访问同一段内存。编译器判断的是最终地址范围，而不是源码名字或语法外形。
* 一次内存访问至少要拆成基址、偏移、访问大小和读写方向。字段、数组下标、指针运算最终都应落到“哪一段字节范围”这个问题上。
* ``MustAlias`` 表示两个访问确定指向同一位置，``NoAlias`` 表示可证明互不重叠，``MayAlias`` 表示当前证据无法排除重叠；部分实现还会区分 ``PartialAlias``。
* ``MayAlias`` 是安全默认值。无法证明独立时，优化器必须保留可能存在的 load/store 依赖和顺序。
* ``NoAlias`` 常为 load reuse、store reordering、LICM、vectorization 等提供独立性证据；``MustAlias`` 则可支撑 store-to-load forwarding、冗余 store 判断等同一位置推理。
* Alias 结论必须与访问方向组合。两个只读访问即使别名也未必冲突；只要其中一个是写操作，就要继续判断是否存在 RAW、WAR 或 WAW 依赖。
* 字段访问可以利用对象布局和偏移证明独立；数组和指针算术会引入动态偏移，通常还需要 range analysis、object bounds 和 provenance 事实。
* 起始地址不同不代表 ``NoAlias``。访问宽度可能导致部分重叠，优化器必须比较完整范围而不是只比较 pointer value。
* 函数参数的 alias 精度通常受调用边界限制。``restrict``、noalias 属性、内联、过程间分析或不同 allocation site 可以给出更强独立性事实。
* 类型信息可以参与 alias 推理，但语言的 strict-aliasing、对象生命周期、union/type-punning 等规则会限制可用结论，不能把“类型不同”机械等同于 ``NoAlias``。
* Alias analysis 本质是保守证明系统：只有证明了独立，优化器才能消费 ``NoAlias``；不确定性不能被当成独立性。
* 每次 CFG、pointer provenance、allocation 或 call-effect 改写都可能改变 alias 事实，相关 analysis 需要更新或失效。

关键路径
--------

别名查询：

::

   memory access A + access B
   → recover base / offset / size
   → inspect object identity and provenance
   → apply range/type/noalias facts
   → MustAlias / PartialAlias / MayAlias / NoAlias
   → combine with read/write direction
   → preserve or remove dependency

Load reuse 判断：

::

   first load
   → intermediate stores/calls
   → alias each clobber against load range
   → prove NoAlias for every interfering write
   → reuse first value

字段与数组：

::

   source field/index expression
   → address computation
   → object + byte offset/range
   → alias query
   → optimization legality

概念辨析
--------

* **Pointer equality 与 aliasing**：两个 pointer value 不必完全相等才发生重叠，范围部分覆盖也属于内存依赖。
* **MustAlias 与 optimization freedom**：确定别名不代表更自由；它常说明一次写入必然影响另一次读取。
* **MayAlias 与“真的会别名”**：MayAlias 只是证据不足，运行时可能重叠也可能完全独立。
* **NoAlias 与源码变量不同名**：名字不同不提供独立性证明；对象来源、范围和语言契约才提供。
* **Alias analysis 与 effect analysis**：前者回答“访问对象是否重叠”，后者回答“操作是否读/写这些对象”，优化通常要同时使用。

本章结论
--------

内存重排和复用必须建立在“已证明独立”上。编译器应把指针、字段和数组访问统一还原成对象与字节范围，再给出 Must/May/NoAlias 结论，并与读写方向组合成真实依赖；只要独立性没有被证明，正确策略就是保留可能存在的内存关系。