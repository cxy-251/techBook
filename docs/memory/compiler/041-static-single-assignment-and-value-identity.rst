第041章：Static Single Assignment and Value Identity
====================================================

核心知识点
----------

* SSA（Static Single Assignment）要求每个 SSA value 只有一个定义点。源码变量可以反复赋值，进入 SSA 后，每次产生的新结果都会获得新的 value identity。
* “Static” 表示单赋值规则约束编译期表示，不代表指令运行时只执行一次；循环中的同一 SSA 定义可以在不同迭代中多次执行。
* 源码变量更像可变槽位，SSA value 更像一次不可改写的计算结果。``x = x + 1`` 在 SSA 中会拆成“读取旧 value → 产生新 value”。
* SSA 的核心收益是把隐含的“当前变量值”改成显式 use-def 关系。一个 use 可以直接追到唯一定义，一个 definition 也可以直接枚举所有 users。
* 直线代码的 SSA 转换主要是重命名：``x0 -> x1 -> x2``。分支合流时还需要 ``phi`` 或 block argument 表达路径相关的当前值。
* SSA 不等于源码不可变变量。可变语言完全可以 lowering 到 SSA；反过来，源码不可变绑定也可能因为取地址、捕获或调试要求以 memory object 存在。
* Register-like value 很适合 SSA 化；memory location 本身通常不直接服从“一个定义”规则。``load`` 产生 SSA value，``store`` 修改内存状态。
* 能否把局部变量从 ``alloca/load/store`` 提升成 SSA，取决于地址是否逃逸、是否存在别名访问、异常/调试约束以及语言内存语义。
* 常量传播在 SSA 中沿 def-use chain 直接传播事实；DCE 可以通过 user list 判断某个纯计算是否无人使用；CSE/GVN 可利用明确 operand identity 判断计算是否等价。
* SSA 只简化值来源问题，不自动解决控制流、内存、副作用、异常、并发与类型语义。任何替换仍需要满足 dominance 和 operation semantics。

关键路径
--------

直线代码 SSA 化：

::

   mutable source variable
   → identify each definition
   → create new SSA value per definition
   → rewrite each use to the dominating current value
   → build explicit def-use graph

优化查询：

::

   use site
   → operand value identity
   → unique defining operation
   → inspect operands / facts
   → propagate or replace
   → update all users

内存提升边界：

::

   local memory slot
   → prove address does not escape / aliases are controlled
   → recover reaching stores
   → replace loads/stores with SSA values
   → insert merge values where needed

概念辨析
--------

* **Source variable 与 SSA value**：前者是语言层可变命名状态，后者是 IR 层一次定义的计算结果。
* **Single assignment 与 single execution**：一个 SSA 名字只定义一次；定义所在指令可以因循环被执行多次。
* **Value identity 与 variable name**：优化器依赖具体定义产生的 value，而不是依赖源码名字是否相同。
* **SSA value 与 memory state**：标量 value 易于唯一化；内存需要 alias/effect 等额外模型。
* **SSA 与 immutability**：SSA 是 IR 组织方式，不是用户语言必须采用不可变变量的要求。

本章结论
--------

SSA 的核心是把“变量当前存什么”改写成“这个 use 明确引用哪个 definition”。当每个 value 都有唯一来源后，use-def、def-use、常量传播、DCE 和等价判断都能直接围绕 value graph 工作；真正困难的部分随后集中到控制流合流、内存和副作用边界上。