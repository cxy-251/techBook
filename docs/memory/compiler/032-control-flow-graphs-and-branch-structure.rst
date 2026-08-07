第032章：Control Flow Graphs and Branch Structure
================================================

核心知识点
----------

* CFG 用 basic block 作为节点，用有向边表示控制可能从一个 block 转移到另一个 block，是函数内部执行可能性的图表示。
* CFG 节点内部保留直线执行顺序，节点之间通过 terminator 表达条件分支、无条件跳转、多路分派、返回、循环回边和异常路径。
* ``if-else`` 会形成分叉与合流；循环会形成 header、body、latch 和 back edge；``switch`` 会形成多路 successor。
* 短路逻辑必须体现求值条件：``A && B`` 只有 A 为真才进入 B，``A || B`` 只有 A 为假才进入 B。
* Return block 终止当前函数路径；异常语义还可能引入 normal edge 之外的 exceptional edge。
* CFG 的图上可达性只证明“存在路径”，路径是否运行时可行还需要常量、范围、类型或其它分析事实。

关键路径
--------

* 先将源码中会改变执行方向的位置切成 block：条件、循环测试、``return``、``break``、``continue``、``switch`` 和异常转移点。
* 读取每个 block 的 terminator，把目标 label 转为 successor 边，并反向得到 predecessor。
* ``if`` 从条件块产生两条边；两个分支若继续共同执行，则在 merge block 合流。
* 循环由条件入口和回边形成：body 或 latch 再次指向 header，header 的失败边通向 loop exit。
* 多个 predecessor 进入同一 block 时，后续数据流和 SSA 分析必须按不同前驱合并输入事实。
* 分析执行可能性时从 entry 沿边遍历，而非按照源码文本或 IR 打印顺序向下阅读。

概念辨析
--------

* CFG 与 AST 不同：AST 主要保存源码嵌套结构，CFG 主要保存执行路径和控制转移关系。
* Branch condition 与 CFG edge 不同：条件值是数据事实，edge 是该条件控制下可能发生的转移。
* Reachable 与 feasible 不同：图上有路表示 reachable，路径条件能够同时成立才表示 feasible。
* Short-circuit 与普通二元运算不同：短路表达式的右操作数是否执行本身属于控制流语义。
* Exception edge 与普通 successor 不同：可能抛出、清理或非本地转移的操作会扩展 CFG 的边集合。

本章结论
--------

CFG 把源码中的结构化控制语法转换成 block 与 edge 的执行图。读控制流时应以 entry、terminator、successor、predecessor、merge、back edge 和 exceptional edge 为证据；程序在图上的实际顺序由可达路径和边条件共同决定。
