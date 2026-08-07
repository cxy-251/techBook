第072章：Parser and Compiler Pipeline Evolution
===============================================

核心知识点
----------

* CPython 的稳定编译主链是：源码文本 → tokenizer → parser → AST → symbol table → compiler/codegen → bytecode/code object → runtime。
* 版本演进时要先判断变化发生在哪一层：语法能力、AST 形状、名字分类、字节码布局、异常表，还是源码位置元数据。
* PEG parser 自 Python 3.9 起成为 CPython 主解析器方向。它允许 grammar 更直接表达复杂语法，并使用有序选择；grammar 分支顺序本身会影响解析行为。
* parser 只判断源码结构是否合法并形成 AST；local、global、free、cell 等名字类别由 symbol table 决定。
* symbol analysis 比 opcode 名称更稳定。一个名字被判定为 local/free/global 的事实，通常比它具体对应 ``LOAD_FAST``、``LOAD_DEREF`` 或某个未来 opcode 名称更值得记忆。
* bytecode 是 CPython 实现细节，不提供跨版本稳定 ABI。Python 3.11 之后，inline cache、quickening、exception table 等结构让 ``dis`` 输出更具版本敏感性。
* Python 3.11 的 zero-cost exception 方向把异常处理范围更多放进 code object 的 exception table，使正常路径不必持续执行旧式 setup 指令。
* PEP 626 强化 bytecode offset 到源码行的精确映射；PEP 657 进一步提供起止行列范围。``co_lines()`` 和 ``co_positions()`` 都属于 compiler 写入 code object 的调试元数据。
* traceback、debugger、coverage、``dis`` 看到的是编译产物的实现痕迹；语言语义仍应从源码、对象模型和异常规则判断。

关键路径
--------

.. code-block:: text

   source
     ↓
   tokenizer
     ↓
   PEG parser
     ↓
   AST
     ↓
   symbol table
     ↓
   compiler / code generation
     ↓
   CFG / instruction sequence / metadata
     ↓
   PyCodeObject
     ├─ bytecode
     ├─ constants / names / locals
     ├─ exception table
     └─ position metadata
     ↓
   frame evaluation

读一个版本差异时，按下面的顺序定位：

#. 先确认目标 Python 版本是否接受该语法。
#. 看 parser/AST 是否改变了语法结构表示。
#. 看 symbol table 是否改变名字绑定分类。
#. 再看 compiler 生成的 instruction、异常表和辅助元数据。
#. 最后才解释 ``dis``、traceback、coverage 或 debugger 的可见差异。

例如 ``try/except`` 的稳定语义是“受保护区域抛出匹配异常后进入 handler”。不同版本可以把这个语义编码成不同 bytecode 和 exception-table 结构。

概念辨析
--------

**PEG parser 与 AST**
   PEG 负责把 token stream 按 grammar 解析；AST 是后续编译阶段消费的结构化语法表示。解析策略变化不等于 Python 对象运行时语义变化。

**symbol table 与 runtime namespace**
   symbol table 在编译期分类名字；runtime namespace 在执行期保存真实对象绑定。编译器决定“去哪里找”，运行时决定“那里当前绑定了什么对象”。

**语言语义与 bytecode**
   ``try``、作用域、函数调用等属于 Python 语义；opcode 名称、cache entry、jump offset 属于 CPython 当前版本实现。

**exception table 与异常对象**
   exception table 是 code object 中的控制流元数据；异常对象仍按 Python 异常模型创建、匹配和传播。

**line metadata 与执行逻辑**
   ``co_lines()``、``co_positions()`` 改善源码定位和工具观察，不负责改变函数计算结果。

本章结论
--------

阅读 compiler 演进时，最稳定的模型不是记 opcode，而是固定“语法 → AST → 名字分类 → code object → frame 执行”这条链。版本变化先定位到链上的具体层，再判断它改变的是语言能力、实现表示还是调试元数据；只要语言语义未变，新的 parser、bytecode、异常表和位置表都只是同一语义的不同实现形态。
