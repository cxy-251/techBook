第017章：Symbol Tables and Scope Chains
======================================

核心知识点
----------

* symbol table 是语义分析阶段建立的名字数据库，记录 name、所属 scope、symbol kind、声明位置、语义 flags、解析目标以及后续存储提示。
* scope chain 由源码静态嵌套结构决定，名字查找通常从当前作用域开始，逐层向外寻找第一个符合语言规则的绑定。
* 同一个名字必须结合“当前观察作用域”分类；local、global、free、cell、captured 都是名字相对某个 scope 的身份。
* 闭包语言中，被内层函数引用的外层局部变量通常需要进入可延长生命周期的环境；外层视角可称 cell/captured，内层视角可称 free variable。
* ``global``、``nonlocal``、模块、类体、块作用域等语言机制会改变普通的向外查找路径，不能只靠词法嵌套机械搜索。
* symbol table 不只服务名字解析，还会被类型检查、闭包转换、IR 生成、局部槽位布局、诊断和 IDE 查询复用。
* 语义阶段对名字的关键产物不是字符串表，而是“声明、作用域、使用点、绑定和存储需求”之间的关系。

关键路径
--------

1. AST 遍历进入 module、function、class 或 block 时创建并压入新的 scope。
2. 收集当前 scope 内的参数、变量、函数、类型、导入等声明，将 symbol 条目写入该作用域。
3. 遍历名字使用点，从当前 scope 查找同名绑定；当前层无结果时按语言规则沿 parent scope 或其它指定路径继续。
4. 对嵌套函数，把未在当前层定义却被使用的名字向外传播，直到找到绑定或进入全局查找边界。
5. 根据引用关系标记 local、global、free、cell/captured 等类别，并确定哪些变量需要闭包环境或特殊存储。
6. 将解析结果挂回 AST 或独立语义表，后续阶段直接使用 symbol ID、scope ID 和变量类别。

概念辨析
--------

* **symbol table vs AST**：AST 记录语法结构；symbol table 把分散在 AST 中的声明与引用整理成可查询语义关系。
* **scope tree vs scope chain**：scope tree 表示静态嵌套全貌；某个使用点向外查找时实际走的是一条 scope chain。
* **local vs free**：local 在当前 scope 建立绑定；free 在当前 scope 被使用，但绑定位于合法外层作用域。
* **free vs global**：free 通常通过词法外层函数环境访问；global 绑定在模块或全局命名空间，不属于闭包捕获路径。
* **cell/captured vs free**：同一变量在外层函数中可能是 cell/captured，在内层函数中则是 free variable。
* **词法作用域 vs 动态查找**：lexical scope 由源码结构决定；动态语言中的某些全局、对象属性或运行时环境仍可能在执行时继续查找。

本章结论
--------

symbol table 把 AST 转换成可复用的名字语义数据库，scope chain 则给每个名字使用点定义稳定查找路径。分析名字问题时，应先确定当前 scope，再找声明、向外解析、判断变量类别，最后检查闭包或运行时存储需求。
