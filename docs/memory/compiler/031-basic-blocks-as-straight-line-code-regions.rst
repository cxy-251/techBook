第031章：Basic Blocks as Straight-Line Code Regions
===================================================

核心知识点
----------

* Basic block 是函数内的直线执行区域：控制从块入口进入后，普通路径按顺序执行到 terminator，中间不存在新的控制流入口或显式分叉。
* Basic block 的边界由控制流决定，而非源码缩进决定：函数入口、跳转目标 label 和 terminator 都会形成切分点。
* Terminator 是 block 的出口合同，典型形式包括条件 ``br``、无条件 ``br``、``ret``、``switch``、``invoke`` 和 ``unreachable``。
* Successor 直接来自 terminator 的目标；predecessor 是同一批 CFG 边的反向关系。文本相邻不等于存在控制流边。
* Entry block 是函数内普通控制流的唯一入口起点；可达性分析从这里开始，函数参数也在此已经可用。
* Block 级优化可以移动、删除、合并或拆分指令区域，但必须同步维护 terminator、label、predecessor、successor、数据依赖和副作用约束。

关键路径
--------

* 源码结构经过 lowering 后，``if``、提前 ``return`` 等结构被拆成 label、普通指令和 terminator。
* 读取 IR 时先定位函数 entry，再按 label 与 terminator 切分 block。
* 对每个 block 读取最后一条 terminator，枚举 successor；再反向建立 predecessor 集合。
* 以 ``entry`` 为起点沿 successor 遍历，即可得到函数当前 CFG 中的可达 block。
* 后续 CFG、dominance、SSA、循环分析和数据流分析都以这些 block 与边作为基础输入。

概念辨析
--------

* Basic block 与源码语句块不同：源码花括号表达词法或结构范围，basic block 表达无内部控制转移的执行区域。
* Label 与 block 不只是打印格式：label 是控制流目标的身份，terminator 对 label 的引用才建立 CFG 边。
* Successor 与文本下一块不同：IR 的执行后继由 terminator 指定，打印顺序只是一种布局。
* ``ret`` 与普通跳转不同：``ret`` 离开当前函数，因此当前函数 CFG 内没有普通 successor。
* Entry block 与普通 block 不同：entry 没有函数内 predecessor，是函数级控制流分析的固定根节点。

本章结论
--------

Basic block 是编译器控制流分析的最小稳定单位。读 IR 时先切 block，再读 terminator 建边；只要 block 边界、前驱后继和出口关系确定，源码中的结构化控制流就已经转换成可分析、可验证、可改写的 CFG 基础结构。
