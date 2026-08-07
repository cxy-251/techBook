第002章：名字绑定与作用域
========================

核心知识点
----------

Python 的名字保存对象引用
   名字绑定是把标识符写入某个 namespace，并使其指向一个对象。赋值不会创建传统意义上的变量槽，同名标识符位于不同 namespace 时是彼此独立的绑定。

绑定操作决定名字所有权
   赋值目标、函数参数、``def``、``class``、``import``、循环目标、``with ... as``、``except ... as``、模式捕获和赋值表达式都会产生绑定。应先确认绑定发生在哪个代码块，再判断读取路径。

普通名字查找遵循 LEGB
   函数中的裸名字通常按 local、enclosing、global、builtins 查找。``obj.attr`` 属于 attribute lookup，``mapping[key]`` 属于 subscription，不能套用 LEGB。

局部名字在编译期确定
   只要函数代码块中存在对某名字的绑定，编译器通常会把它归为 local，即使绑定语句位于读取语句之后。读取尚未建立值的 local 会触发 ``UnboundLocalError``，不会回退到 global。

闭包保存外层绑定通道
   内层函数读取外层函数名字时，该名字在内层成为 free variable，在外层成为 cell variable。closure 持有 cell，使外层调用结束后仍可读取或通过 ``nonlocal`` 更新该绑定。

闭包默认采用后期读取
   多个函数捕获同一个循环变量时，它们共享同一个 cell，调用时读取 cell 的当前对象。需要冻结每轮值时，可在函数创建时通过默认参数建立独立绑定。

``global`` 与 ``nonlocal`` 改变绑定归属
   ``global`` 使当前代码块中的指定名字读写模块 namespace；``nonlocal`` 使名字指向最近的 enclosing function scope。二者是编译期声明，不是运行期查找补丁。

推导式拥有隐式作用域
   推导式循环变量绑定在隐式嵌套 scope 中，不泄漏到外层；最左侧 iterable 表达式在外层 scope 求值。推导式不能把 class namespace 当作普通 enclosing function scope。

关键路径
--------

名字分类与访问：

::

   解析 module、function、class、comprehension 等代码块
   → 收集每个代码块中的绑定操作
   → 应用 global 与 nonlocal 声明
   → 把名字分类为 local、global、free、cell 等
   → 生成对应访问方式
   → 运行期从 frame local、closure cell、module globals 或 builtins 取得对象

闭包形成路径：

::

   外层函数建立局部绑定
   → 内层函数读取该名字
   → 外层绑定转换为 cell
   → 内层 function object 保存 closure 引用
   → 外层 frame 退出
   → cell 仍保存绑定并供后续调用读取或更新

概念辨析
--------

* **namespace 与 scope**：namespace 保存绑定；scope 决定源码中的可见范围。二者相关，但一个是运行时映射，一个是名字解析边界。
* **绑定与查找**：绑定决定名字归属；查找根据已确定的归属取得对象。``UnboundLocalError`` 正是名字已归为 local、但值尚未绑定的结果。
* **free variable 与 cell variable**：内层函数读取的外层名字是 free variable；提供该绑定并被内层捕获的外层名字是 cell variable。
* **``global`` 与 ``nonlocal``**：``global`` 指向模块 namespace；``nonlocal`` 指向最近的外层函数绑定，不能直接创建不存在的外层绑定。
* **循环变量与推导式变量**：普通 ``for`` target 绑定在当前 scope；推导式 target 绑定在隐式嵌套 scope。

本章结论
--------

排查名字问题时，应先划分代码块并列出绑定操作，再应用 ``global``、``nonlocal`` 和推导式边界，最后把编译期分类映射到 local、cell、global 与 builtins；闭包问题则要继续检查多个函数是否共享同一个 cell，而不是假设捕获了创建时的值副本。
