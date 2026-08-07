第020章：Semantic Errors Beyond Syntax
=====================================

核心知识点
----------

* semantic error 指源码已经形成合法 AST，但该结构缺少语言允许的意义；判断依据来自名字、声明、作用域、控制流上下文和访问规则。
* undefined name 与 unbound variable 都发生在名字使用点无法获得有效绑定时；诊断应给出使用位置、查找路径和失败名字。
* duplicate declaration 与 conflicting definition 发生在向 symbol table 插入新声明时发现当前语义位置已有不兼容实体。
* 控制流上下文错误来自语句与环境不匹配，例如 ``break`` 缺少 loop/switch 目标，``return`` 缺少函数上下文，``await`` 缺少 async 上下文。
* 语义遍历需要维护 function、loop、switch、generator、async 等上下文栈；新的函数或闭包边界不能错误继承外层控制流目标。
* visibility/access error 的特点是目标实体已经成功解析，随后因为 private、module visibility、capability 等规则被拒绝。
* 高质量语义诊断应同时保存当前错误位置、相关声明位置、所违反规则和可行动的修复方向。

关键路径
--------

1. Parser 先生成 AST；语义分析逐节点遍历，并携带当前 scope、symbol table、控制流上下文和访问者身份。
2. 遇到名字使用点时执行 name resolution；找不到合法声明则报告 undefined/unresolved name。
3. 遇到新声明时检查当前语义 scope 的已有 symbol，判断同名实体是否可合并、重载、补全或构成冲突。
4. 遇到 ``break``、``continue``、``return``、``yield``、``await`` 等节点时查询上下文栈，确认存在合法目标且没有跨越语言禁止的边界。
5. 成员或模块名字解析成功后执行 visibility/capability 检查；失败时保留目标声明位置和当前访问位置。
6. 将错误节点标记为可恢复状态，尽量继续分析其它独立 AST 区域，避免一个根因制造大量级联诊断。

概念辨析
--------

* **syntax error vs semantic error**：前者无法按 grammar 构造合法结构；后者已有 AST，但结构违反名字、作用域、类型前置或上下文规则。
* **undefined vs uninitialized**：undefined 表示没有可用声明绑定；uninitialized 表示声明已经存在，但值尚未满足使用条件，后者通常还需要 definite-assignment/data-flow 分析。
* **duplicate declaration vs legal redeclaration/overload**：同名本身不是错误，关键在实体类别、scope、签名与语言允许的合并规则。
* **control-flow nesting vs lexical nesting**：外层循环在语法上包围一个 lambda，并不意味着 lambda 内的 ``break`` 可以跳出该循环。
* **unresolved name vs access violation**：前者找不到目标；后者目标已知，只是当前访问位置没有权限。
* **semantic diagnostic vs parser recovery**：parser 恢复结构断点；semantic recovery 在 AST 已存在的前提下标记错误实体并继续其它语义检查。

本章结论
--------

语义分析把“结构合法”推进到“程序有意义”。排查语法之后的编译错误时，应先定位 AST 节点，再检查名字绑定、声明兼容性、控制流上下文与访问规则；每类错误都应能追溯到明确的语义状态和相关声明证据。
